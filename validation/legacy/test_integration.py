#!/usr/bin/env python
"""
Deterministic core-runtime smoke test for ApexQuantumICT.

Validates the market adapter, operator registry, path engine, scheduler,
constraints, and shadow execution flow without touching brokers or external APIs.
"""

import random

import numpy as np

from trading.evidence.evidence_chain import EvidenceEmitter
from trading.kernel.H_constraints import ConstraintHamiltonian
from trading.kernel.scheduler import Scheduler
from trading.market_bridge.market_data_adapter import MarketDataAdapter
from trading.operators.operator_registry import OperatorRegistry
from trading.path_integral.trajectory_generator import PathIntegralEngine
from trading.shadow.shadow_trading_loop import ShadowExecution, ShadowTradingLoop


def make_ohlcv(symbol: str, n: int = 24) -> list[dict]:
    """Build deterministic synthetic OHLCV candles for local validation."""
    price = 1.0850 if "USD" in symbol else 100.0
    candles = []
    for i in range(n):
        drift = 0.00015 if i % 3 == 0 else -0.00005
        noise = random.gauss(0, 0.0002)
        open_p = price
        close_p = price + drift + noise
        high_p = max(open_p, close_p) + abs(random.gauss(0, 0.0001))
        low_p = min(open_p, close_p) - abs(random.gauss(0, 0.0001))
        candles.append({
            "open": round(open_p, 5),
            "high": round(high_p, 5),
            "low": round(low_p, 5),
            "close": round(close_p, 5),
            "volume": 1000 + i * 25,
            "timestamp": i,
        })
        price = close_p
    return candles


random.seed(12345)
np.random.seed(12345)

print("=" * 60)
print("ApexQuantumICT Deterministic Core Runtime Smoke Test")
print("=" * 60)

symbol = "EURUSD"
ohlcv = make_ohlcv(symbol)

# Test 1: Core component initialization
print("\n[TEST 1] Core Components...")
registry = OperatorRegistry()
path_engine = PathIntegralEngine()
constraints = ConstraintHamiltonian()
scheduler = Scheduler()
shadow = ShadowTradingLoop()
emitter = EvidenceEmitter()

assert len(registry.operators) == 25, f"Expected 25 operators, got {len(registry.operators)}"
assert len(registry._legacy_operator_names) == 18, "Legacy O1-O18 operator slice changed"
assert constraints.get_admissibility_status()["projector_count"] > 0, "Missing constraint projectors"
assert scheduler.get_scheduler_status()["refusal_first"] is True, "Scheduler refusal-first disabled"
assert emitter is not None, "Evidence emitter failed to initialize"
print(f"  OK - Loaded {len(registry.operators)} operators (18 legacy + 7 order-book)")
print("  OK - Scheduler, constraints, shadow loop, and evidence emitter initialized")

# Test 2: Market data adapter
print("\n[TEST 2] Market Data Adapter...")
adapter = MarketDataAdapter()
market_state = adapter.adapt(ohlcv)
assert "_tuple" in market_state, "Minkowski tuple missing"
assert market_state.get("ohlc"), "Market state missing OHLC payload"
assert market_state.get("opens"), "Market state missing opens"
assert market_state.get("closes"), "Market state missing closes"
print(f"  OK - Adapted {len(market_state.get('prices', []))} prices into market state")

# Test 3: Path integral execution
print("\n[TEST 3] Path Integral Engine...")
hamiltonian = registry.get_hamiltonian(market_state, {})
path_result = path_engine.execute_path_integral(
    initial_state={"price": market_state.get("close", 0.0), "velocity": 0.0},
    hamiltonian=hamiltonian,
    operator_registry=registry,
)
trajectories = path_result.get("trajectories", [])
assert trajectories, "No trajectories generated"
assert path_result.get("best_trajectory") is not None, "Missing best trajectory"
print(f"  OK - Generated {len(trajectories)} trajectories")

# Test 4: Setup analysis
print("\n[TEST 4] Setup Analysis...")
analysis = shadow.analyze_setup(symbol, ohlcv)
assert analysis, "Empty analysis payload"
assert analysis.get("setup_quality"), "Missing setup_quality"
assert analysis["setup_quality"].get("top_signals"), "Missing top_signals"
print(f"  OK - Recommendation: {analysis['recommendation']}")
for name, score in analysis["setup_quality"]["top_signals"][:3]:
    print(f"    - {name}: {score:.3f}")

# Test 5: Shadow execution
print("\n[TEST 5] Shadow Execution...")
execution = shadow.execute_shadow(symbol, ohlcv, "bullish", "london")
assert isinstance(execution, ShadowExecution), f"Unexpected execution type: {type(execution)}"
assert execution.outcome.value in {"success", "refused"}, f"Unexpected outcome: {execution.outcome.value}"
assert execution.evidence_hash, "Missing evidence hash"
assert isinstance(execution.execution_time_ms, (int, float)), "Execution time is not numeric"
print(f"  OK - Outcome: {execution.outcome.value}")
print(f"  OK - Evidence: {execution.evidence_hash[:16]}...")
print(f"  OK - Execution time: {execution.execution_time_ms:.2f}ms")

# Test 6: System report
print("\n[TEST 6] Shadow System Report...")
report = shadow.get_shadow_report()
assert report["performance"]["total_executions"] >= 1, "Execution counter did not update"
print(f"  OK - Total executions: {report['performance']['total_executions']}")
print("  OK - Deterministic evidence and refusal-first flow verified")

print("\n" + "=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
