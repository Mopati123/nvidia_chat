#!/usr/bin/env python3
"""
Test script for Vector DB Pattern Memory Integration

Verifies:
1. Market embedder creates valid embeddings
2. Vector store stores and retrieves patterns
3. Memory bias computation works
4. Integration with trajectory generator
"""

import sys
sys.path.insert(0, '.')

import numpy as np
from datetime import datetime

def test_embedder():
    """Test market state embedder"""
    print("\n" + "="*70)
    print("🧪 TEST 1: Market Embedder")
    print("="*70)
    
    from trading.memory import get_embedder, reset_embedder
    
    # Reset to ensure fresh embedder instance
    reset_embedder()
    
    # Create sample OHLCV data
    ohlcv = []
    base_price = 1.0850
    for i in range(100):
        noise = np.random.normal(0, 0.001)
        close = base_price + noise + (i * 0.0001)  # Slight uptrend
        ohlcv.append({
            'open': close - 0.0001,
            'high': close + 0.0002,
            'low': close - 0.0002,
            'close': close,
            'volume': 1000 + i * 10
        })
    
    embedder = get_embedder()
    embedding = embedder.encode(ohlcv)
    
    print(f"✅ Embedding shape: {embedding.shape}")
    print(f"✅ Embedding norm: {np.linalg.norm(embedding):.4f} (should be ~1.0)")
    print(f"✅ Embedding range: [{embedding.min():.4f}, {embedding.max():.4f}]")
    
    # Test similarity
    embedding2 = embedder.encode(ohlcv)
    similarity = embedder.compute_similarity(embedding, embedding2)
    print(f"✅ Self-similarity: {similarity:.4f} (should be ~1.0)")
    
    return True


def test_vector_store():
    """Test pattern vector store"""
    print("\n" + "="*70)
    print("🧪 TEST 2: Pattern Vector Store")
    print("="*70)
    
    from trading.memory import get_vector_store, get_embedder
    
    # Reset to get fresh instance
    from trading.memory import reset_vector_store
    reset_vector_store()
    
    store = get_vector_store(collection_name="test_patterns")
    embedder = get_embedder()
    
    # Create and store some patterns
    symbols = ['EURUSD', 'GBPUSD', 'EURUSD', 'USDJPY']
    timeframes = ['1h', '1h', '15m', '1h']
    
    pattern_ids = []
    for i, (symbol, tf) in enumerate(zip(symbols, timeframes)):
        # Generate random embedding
        embedding = np.random.randn(128)
        embedding = embedding / np.linalg.norm(embedding)
        
        # Create fake trajectory outcomes
        trajectories = [
            {
                'trajectory_id': f'traj_{j}',
                'pnl': np.random.randn() * 0.01,
                'success': np.random.random() > 0.5,
                'operators_used': ['kinetic', 'liquidity']
            }
            for j in range(3)
        ]
        
        pattern_id = store.store_pattern(
            embedding=embedding,
            symbol=symbol,
            timeframe=tf,
            trajectories=trajectories,
            market_summary={'trend': 0.01, 'volatility': 0.02},
            evidence_hash=f"hash_{i}"
        )
        pattern_ids.append(pattern_id)
        print(f"✅ Stored pattern {pattern_id} for {symbol}")
    
    # Test query
    print("\n📡 Querying similar patterns for EURUSD...")
    query_embedding = np.random.randn(128)
    query_embedding = query_embedding / np.linalg.norm(query_embedding)
    
    similar = store.query_similar(
        query_embedding,
        symbol='EURUSD',
        timeframe='1h',
        top_k=5
    )
    
    print(f"✅ Retrieved {len(similar)} similar patterns")
    for s in similar:
        sim = s.market_summary.get('similarity', 0)
        print(f"   - {s.pattern_id}: {s.symbol} ({sim:.3f} similarity)")
    
    # Test stats
    stats = store.get_stats()
    print(f"\n📊 Store stats: {stats}")
    
    return True


def test_memory_bias():
    """Test memory bias computation"""
    print("\n" + "="*70)
    print("🧪 TEST 3: Memory Bias Computation")
    print("="*70)
    
    from trading.memory import get_vector_store
    from trading.path_integral import Trajectory
    
    store = get_vector_store()
    
    # Create fake trajectories
    class FakeTrajectory:
        def __init__(self, traj_id, ops):
            self.id = traj_id
            self.operators_used = ops
            self.operator_scores = {op: 1.0 for op in ops}
    
    trajectories = [
        FakeTrajectory('traj_1', ['kinetic', 'liquidity']),
        FakeTrajectory('traj_2', ['kinetic', 'ob']),
        FakeTrajectory('traj_3', ['liquidity', 'fvg']),
    ]
    
    # Create fake memories
    from trading.memory.vector_store import PatternMemory
    memories = [
        PatternMemory(
            pattern_id='mem_1',
            timestamp=datetime.now().isoformat(),
            symbol='EURUSD',
            timeframe='1h',
            embedding_hash='hash1',
            trajectories=[{
                'trajectory_id': 'traj_1',
                'pnl': 0.05,
                'success': True,
                'operators_used': ['kinetic', 'liquidity']
            }],
            best_trajectory_id='traj_1',
            best_pnl=0.05,
            avg_pnl=0.03,
            win_rate=1.0,
            market_summary={'similarity': 0.85},
            evidence_hash='ev1'
        )
    ]
    
    biases = store.compute_memory_bias(
        trajectories,
        memories,
        bias_strength=0.3
    )
    
    print(f"✅ Computed biases for {len(biases)} trajectories:")
    for tid, bias in biases.items():
        print(f"   - {tid}: {bias:.4f}")
    
    return True


def test_trajectory_generator_integration():
    """Test integration with trajectory generator"""
    print("\n" + "="*70)
    print("🧪 TEST 4: Trajectory Generator Integration")
    print("="*70)
    
    from trading.path_integral import PathIntegralEngine
    
    # Try to import OperatorRegistry, create mock if not available
    try:
        from trading.operators import OperatorRegistry
        operator_registry = OperatorRegistry()
    except (ImportError, AttributeError):
        print("⚠️ OperatorRegistry not available, using mock")
        class MockOperatorRegistry:
            def get_all_scores(self, market_data, context):
                return {'kinetic': 0.5, 'potential': 0.3, 'ob': 0.2}
        operator_registry = MockOperatorRegistry()
    
    # Create engine with memory enabled
    engine = PathIntegralEngine(use_memory=True)
    
    # Sample market state
    initial_state = {
        'price': 1.0850,
        'velocity': 0.0,
        'time': 0.0
    }
    
    hamiltonian = {
        'kinetic': 0.5,
        'potential': 1.0,
        'liquidity': 0.3,
        'force': 0.01
    }
    
    # Sample OHLCV
    ohlcv = []
    for i in range(100):
        ohlcv.append({
            'open': 1.0840 + i * 0.0001,
            'high': 1.0845 + i * 0.0001,
            'low': 1.0835 + i * 0.0001,
            'close': 1.0842 + i * 0.0001,
            'volume': 1000
        })
    
    # Execute with memory
    result = engine.execute_path_integral(
        initial_state=initial_state,
        hamiltonian=hamiltonian,
        operator_registry=operator_registry,
        ohlcv_data=ohlcv,
        symbol='EURUSD',
        timeframe='1h'
    )
    
    print(f"✅ Generated {result['trajectory_count']} trajectories")
    print(f"✅ Memory augmented: {result['memory_augmented']}")
    print(f"✅ Epsilon (ℏ): {result['epsilon']:.6f}")
    
    if result['best_trajectory']:
        best = result['best_trajectory']
        print(f"✅ Best trajectory: {best['id']}")
        print(f"✅ Best action score: {best.get('action_score', 'N/A')}")
        print(f"✅ Memory bias: {best.get('memory_bias', 'N/A')}")
    
    # Test storing outcome
    pattern_id = engine.store_execution_outcome(
        ohlcv_data=ohlcv,
        symbol='EURUSD',
        timeframe='1h',
        trajectories=engine.memory_generator.generator.generate_trajectories(
            initial_state, hamiltonian, operator_registry
        ) if engine.memory_generator else [],
        evidence_hash="test_evidence_123"
    )
    
    if pattern_id:
        print(f"✅ Stored pattern outcome: {pattern_id}")
    
    return True


def main():
    """Run all tests"""
    print("="*70)
    print("🚀 PATTERN MEMORY INTEGRATION TEST SUITE")
    print("="*70)
    
    tests = [
        ("Market Embedder", test_embedder),
        ("Vector Store", test_vector_store),
        ("Memory Bias", test_memory_bias),
        ("Trajectory Integration", test_trajectory_generator_integration),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
                print(f"\n✅ {name}: PASSED")
            else:
                failed += 1
                print(f"\n❌ {name}: FAILED")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name}: ERROR - {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print(f"📊 RESULTS: {passed} passed, {failed} failed")
    print("="*70)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
