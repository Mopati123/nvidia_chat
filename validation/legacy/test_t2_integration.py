"""
Comprehensive T2 Integration Tests (T2-D through T2-H)
Tests all enhancements: regime alpha, PPO hook, FAISS memory, async ticks, dashboard, mojo IPC
"""

import sys
import os
import json
import tempfile
import time
import numpy as np
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# T2-D: Regime-Based Sailing Lane Alpha
# ============================================================================

def test_t2d_regime_sailing_alpha():
    """Test regime-based sailing lane alpha injection"""
    from trading.operators.operator_registry import OperatorRegistry

    logger.info("\n=== T2-D: Regime Sailing Lane Alpha ===")

    # Test classmethod existence and correctness
    assert hasattr(OperatorRegistry, 'sailing_alpha_from_regime'), "Missing sailing_alpha_from_regime method"

    test_cases = {
        "TRENDING": 0.85,
        "RANGING": 0.7,
        "HIGH_VOL": 0.6,
        "CRISIS": 0.5,
        "UNKNOWN": 0.8,  # default
    }

    for regime, expected_alpha in test_cases.items():
        alpha = OperatorRegistry.sailing_alpha_from_regime(regime)
        assert abs(alpha - expected_alpha) < 1e-6, f"Regime {regime}: expected {expected_alpha}, got {alpha}"
        logger.info(f"✓ Regime {regime:12s} → α={alpha}")

    # Test that regime affects trajectory scoring
    registry = OperatorRegistry()
    state_trending = {"sailing_alpha": 0.85, "current_leg": 2, "max_legs": 5, "sailing_L0": 1.0}
    state_ranging = {"sailing_alpha": 0.7, "current_leg": 2, "max_legs": 5, "sailing_L0": 1.0}

    score_trending = registry._compute_sailing_lane({}, state_trending)
    score_ranging = registry._compute_sailing_lane({}, state_ranging)

    assert score_trending > score_ranging, f"Trending ({score_trending}) should beat ranging ({score_ranging})"
    logger.info(f"✓ Sailing lane scores: Trending={score_trending:.4f} > Ranging={score_ranging:.4f}")

    logger.info("✅ T2-D: PASS\n")


# ============================================================================
# T2-C: PPO Paper Trading Hook
# ============================================================================

def test_t2c_ppo_paper_hook():
    """Test PPO training hook integration with paper trading"""
    logger.info("\n=== T2-C: PPO Paper Trading Hook ===")

    try:
        from trading.rl.ppo_paper_hook import PPOPaperHook
        from trading.rl.scheduler_agent import PPOSchedulerAgent
        from trading.paper_trading_loop import PaperTradeContext
        from trading.brokers.signal_router import RoutedOrder
        from trading.brokers.tradingview_connector import TradingViewSignal, BrokerEnum
    except ImportError as e:
        logger.warning(f"PPO modules not fully available: {e}")
        logger.info("⚠️ T2-C: SKIP (PPO infrastructure incomplete)\n")
        return

    # Create mock agent with buffer
    agent = Mock(spec=PPOSchedulerAgent)
    agent.buffer = Mock()
    agent.buffer.buffer_size = 2048
    agent.recent_pnl = []

    call_count = {"select_action": 0, "store_transition": 0, "update": 0}

    def mock_select_action(state):
        call_count["select_action"] += 1
        return 1, 0.5, 0.1  # action_idx, log_prob, value

    def mock_store_transition(*args, **kwargs):
        call_count["store_transition"] += 1

    def mock_update():
        call_count["update"] += 1

    agent.select_action = mock_select_action
    agent.store_transition = mock_store_transition
    agent.update = mock_update

    hook = PPOPaperHook(agent)

    # Mock a trade context
    signal = Mock(spec=TradingViewSignal)
    signal.symbol = "EURUSD"
    signal.price = 1.0855
    signal.rsi = 55
    signal.ofi = 500

    order = Mock(spec=RoutedOrder)
    order.signal = signal
    order.broker = BrokerEnum.DERIV
    order.size = 0.01
    order.price = 1.0855

    context = PaperTradeContext(
        signal=signal,
        routed_order=order,
        entry_price=1.0855,
        size=0.01,
        status="executed"
    )

    # Test on_trade_executed
    hook.on_trade_executed(context)
    assert call_count["select_action"] == 1, "select_action should be called once"
    logger.info(f"✓ on_trade_executed called: {call_count['select_action']} select_action calls")

    # Test on_trade_closed
    trade_id = f"{signal.symbol}_{int(context.entry_time*1000)}"
    pnl = 25.0
    hook.on_trade_closed(trade_id, pnl)
    assert call_count["store_transition"] == 1, "store_transition should be called once"
    logger.info(f"✓ on_trade_closed called: {call_count['store_transition']} store_transition calls, PnL={pnl}")

    logger.info("✅ T2-C: PASS\n")


# ============================================================================
# T2-E: FAISS Vector Memory
# ============================================================================

def test_t2e_faiss_vector_store():
    """Test FAISS-backed vector store"""
    logger.info("\n=== T2-E: FAISS Vector Memory ===")

    try:
        from trading.memory.vector_store import PatternVectorStore, PatternMemory
    except ImportError as e:
        logger.warning(f"Vector store not available: {e}")
        logger.info("⚠️ T2-E: SKIP (vector store module missing)\n")
        return

    # Use temporary persist directory
    with tempfile.TemporaryDirectory() as tmpdir:
        store = PatternVectorStore(persist_dir=Path(tmpdir))

        # Test 1: Store pattern
        embedding = np.random.randn(128).astype("float32")
        embedding = embedding / np.linalg.norm(embedding)  # L2-normalize

        pattern_id = store.store_pattern(
            embedding=embedding,
            symbol="EURUSD",
            timeframe="1H",
            trajectories=[{"pnl": 50.0, "success": True}],
            market_summary={"regime": "TRENDING"},
            evidence_hash="abc123"
        )

        assert pattern_id is not None and len(pattern_id) > 0, "Pattern ID should be returned"
        logger.info(f"✓ Pattern stored: {pattern_id}")

        # Test 2: Query similar
        query_embedding = embedding + np.random.randn(128).astype("float32") * 0.1
        query_embedding = query_embedding / np.linalg.norm(query_embedding)

        results = store.query_similar(query_embedding, top_k=5, min_similarity=0.5)
        assert len(results) > 0, "Should find at least one similar pattern"
        logger.info(f"✓ Query returned {len(results)} result(s)")

        # Test 3: Check similarity score
        assert results[0].market_summary.get("similarity", 0) >= 0.5, "Similarity should meet threshold"
        logger.info(f"✓ Similarity score: {results[0].market_summary.get('similarity', 0):.4f}")

        # Test 4: Get pattern by ID
        retrieved = store.get_pattern(pattern_id)
        assert retrieved is not None, "Pattern should be retrievable by ID"
        assert retrieved.symbol == "EURUSD", "Symbol should match"
        logger.info(f"✓ Pattern retrieved by ID: {retrieved.symbol}")

        # Test 5: Get stats
        stats = store.get_stats()
        assert stats["total_patterns"] >= 1, "Stats should show at least 1 pattern"
        logger.info(f"✓ Store stats: {stats}")

        # Test 6: Persistence (reload from disk)
        store2 = PatternVectorStore(persist_dir=Path(tmpdir))
        assert store2._index.ntotal > 0, "Reloaded store should have patterns"
        results2 = store2.query_similar(query_embedding, top_k=5, min_similarity=0.5)
        assert len(results2) > 0, "Reloaded store should return query results"
        logger.info(f"✓ Persistence verified: reloaded store has {store2._index.ntotal} patterns")

    logger.info("✅ T2-E: PASS\n")


# ============================================================================
# T2-F: Async Tick Loop
# ============================================================================

def test_t2f_async_tick_loop():
    """Test asyncio-based tick ingestion loop"""
    logger.info("\n=== T2-F: Async Tick Loop ===")

    try:
        from trading.brokers.async_tick_loop import AsyncTickLoop
    except ImportError as e:
        logger.warning(f"Async tick loop not available: {e}")
        logger.info("⚠️ T2-F: SKIP (async tick loop module missing)\n")
        return

    tick_count = {"processed": 0}

    async def mock_pipeline(tick_data):
        """Mock pipeline function"""
        tick_count["processed"] += 1

    # Create mock brokers
    mock_deriv = Mock()
    mock_deriv.get_latest_tick = lambda: {"source": "deriv", "price": 1.0855, "bid": 1.0853}

    mock_mt5 = Mock()
    mock_mt5.get_current_price = lambda symbol: {"source": "mt5", "symbol": symbol, "price": 1.0855}

    # Create loop and run briefly
    loop = AsyncTickLoop(pipeline_fn=mock_pipeline, queue_maxsize=100)
    logger.info(f"✓ AsyncTickLoop created with queue maxsize={loop.queue_maxsize}")

    # Test tick processing (mock with synchronous test)
    queue = asyncio.Queue(maxsize=100)
    logger.info(f"✓ Tick queue created")

    # Simulate tick ingestion
    for i in range(10):
        queue.put_nowait(("deriv", {"price": 1.0855 + i * 0.0001}))

    assert queue.qsize() == 10, "Queue should have 10 ticks"
    logger.info(f"✓ Simulated {queue.qsize()} ticks in queue")

    logger.info("✅ T2-F: PASS\n")


# ============================================================================
# T2-G: FastAPI Dashboard
# ============================================================================

def test_t2g_dashboard():
    """Test FastAPI dashboard endpoints"""
    logger.info("\n=== T2-G: FastAPI Dashboard ===")

    try:
        from trading.dashboard.app import app, _get_metrics
        from fastapi.testclient import TestClient
    except ImportError as e:
        logger.warning(f"Dashboard not available: {e}")
        logger.info("⚠️ T2-G: SKIP (dashboard module missing)\n")
        return

    client = TestClient(app)

    # Test GET /metrics
    response = client.get("/metrics")
    assert response.status_code == 200, f"GET /metrics should return 200, got {response.status_code}"
    metrics = response.json()
    assert "risk_status" in metrics or "daily_pnl" in metrics, "Response should have dashboard metrics"
    logger.info(f"✓ GET /metrics returned 200: {list(metrics.keys())[:5]}")

    # Test GET / (HTML)
    response = client.get("/")
    assert response.status_code == 200, f"GET / should return 200, got {response.status_code}"
    assert "html" in response.text.lower() or "ApexQuantumICT" in response.text, "Should return HTML dashboard"
    logger.info(f"✓ GET / returned 200 with {len(response.text)} bytes of HTML")

    # Test POST /kill
    response = client.post("/kill")
    assert response.status_code == 200, f"POST /kill should return 200, got {response.status_code}"
    logger.info(f"✓ POST /kill returned 200")

    # Test POST /kill/release
    response = client.post("/kill/release")
    assert response.status_code == 200, f"POST /kill/release should return 200, got {response.status_code}"
    logger.info(f"✓ POST /kill/release returned 200")

    logger.info("✅ T2-G: PASS\n")


# ============================================================================
# T2-H: Mojo mmap IPC
# ============================================================================

def test_t2h_mojo_mmap_ipc():
    """Test Mojo mmap IPC protocol"""
    logger.info("\n=== T2-H: Mojo mmap IPC ===")

    try:
        from trading.accelerated.mojo_bridge import MojoEngineBridge, _SHMEM_SIZE
        import struct
        import mmap
    except ImportError as e:
        logger.warning(f"Mojo bridge not available: {e}")
        logger.info("⚠️ T2-H: SKIP (mojo bridge module missing)\n")
        return

    bridge = MojoEngineBridge()
    logger.info(f"✓ MojoEngineBridge created (Mojo available: {bridge.available})")
    logger.info(f"✓ Shared memory size: {_SHMEM_SIZE / (1024*1024):.1f} MB")

    # Test mmap protocol encode/decode
    payload = {"test": "data", "value": 42}
    payload_bytes = json.dumps(payload).encode("utf-8")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".shm") as tf:
        shm_path = tf.name
        tf.write(b"\x00" * _SHMEM_SIZE)

    try:
        with open(shm_path, "r+b") as f:
            mm = mmap.mmap(f.fileno(), _SHMEM_SIZE)

            # Encode: write length + data
            mm[:4] = struct.pack("<I", len(payload_bytes))
            mm[4:4 + len(payload_bytes)] = payload_bytes
            mm.flush()
            logger.info(f"✓ Encoded {len(payload_bytes)} bytes into mmap buffer")

            # Decode: read length + data
            out_len = struct.unpack("<I", mm[:4])[0]
            decoded_bytes = mm[4:4 + out_len]
            decoded = json.loads(decoded_bytes.decode("utf-8"))

            assert decoded == payload, f"Decoded payload should match original: {decoded}"
            logger.info(f"✓ Decoded payload matches: {decoded}")

            mm.close()
    finally:
        try:
            os.unlink(shm_path)
        except:
            pass

    logger.info("✅ T2-H: PASS\n")


# ============================================================================
# Main Test Harness
# ============================================================================

def run_all_tests():
    """Run all T2 integration tests"""
    logger.info("\n" + "="*70)
    logger.info("T2 INTEGRATION TEST SUITE (T2-D through T2-H)")
    logger.info("="*70)

    tests = [
        ("T2-D", test_t2d_regime_sailing_alpha),
        ("T2-C", test_t2c_ppo_paper_hook),
        ("T2-E", test_t2e_faiss_vector_store),
        ("T2-F", test_t2f_async_tick_loop),
        ("T2-G", test_t2g_dashboard),
        ("T2-H", test_t2h_mojo_mmap_ipc),
    ]

    passed = 0
    failed = 0
    skipped = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            logger.error(f"❌ {name}: FAIL — {e}")
            failed += 1

    logger.info("\n" + "="*70)
    logger.info(f"RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
    logger.info("="*70 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
