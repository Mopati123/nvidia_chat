# Examples — ApexQuantumICT

Working Python code snippets. All examples assume you are in the `nvidia_chat/` root directory with dependencies installed.

---

## Example 1: Execute One Pipeline Cycle

Run the full 20-stage pipeline on synthetic market data.

```python
import time
from trading.pipeline.orchestrator import PipelineOrchestrator

orch = PipelineOrchestrator()

raw_data = {
    "open":   [1.0850, 1.0852, 1.0855, 1.0858, 1.0860],
    "high":   [1.0860, 1.0863, 1.0868, 1.0870, 1.0875],
    "low":    [1.0845, 1.0848, 1.0850, 1.0853, 1.0856],
    "close":  [1.0855, 1.0858, 1.0862, 1.0865, 1.0868],
    "volume": [1200, 1350, 980, 1100, 1420],
    "time":   [time.time() - 300 + i*60 for i in range(5)]
}

ctx = orch.execute(raw_data, symbol="EURUSD", source="MT5")

print("Decision:  ", ctx.collapse_decision)
print("Proposal:  ", ctx.proposal)
print("Duration:  ", ctx.duration_ms, "ms")
print("Regime:    ", ctx.regime.value if ctx.regime else "N/A")
print("Stages:    ", len(ctx.stage_history))
```

Expected output:
```
Decision:   AUTHORIZED
Proposal:   {'direction': 'buy', 'entry': 1.0868, 'stop': 1.0845, 'target': 1.0912, 'size': 0.1, 'predicted_pnl': 44.0}
Duration:   12.4 ms
Regime:     TRENDING
Stages:     20
```

---

## Example 2: Check Risk Limits Before Trading

```python
from trading.risk.risk_manager import get_risk_manager

rm = get_risk_manager()

check = rm.check_all_limits(
    symbol="EURUSD",
    direction="buy",
    size=0.1,
    price=1.0855
)

print("Passed:", check.passed)
print("Level: ", check.level.value)   # GREEN | YELLOW | RED | KILL
print("Reason:", check.message)
```

Check with a position that exceeds limits:
```python
big_check = rm.check_all_limits("EURUSD", "buy", size=10.0, price=1.0855)
print("Blocked:", not big_check.passed)
print("Limit:  ", big_check.limit, "lots")
print("Value:  ", big_check.value, "lots requested")
```

---

## Example 3: Track PnL and Execution Errors

```python
import time
from trading.risk.pnl_tracker import get_pnl_tracker, TradeRecord

pt = get_pnl_tracker()

# Simulate a completed trade
trade = TradeRecord(
    trade_id="example_001",
    symbol="EURUSD",
    direction="buy",
    entry_price=1.0855,
    exit_price=1.0882,
    size=0.1,
    realized_pnl=27.0,
    entry_time=time.time() - 3600,
    exit_time=time.time(),
    broker="deriv"
)
pt.record_trade(trade)

# Record the prediction error
pt.record_execution_error(predicted_pnl=30.0, realized_pnl=27.0)

# Get stats
stats = pt.get_divergence_stats()
print("Divergence stats:", stats)
# {'mean': 0.10, 'std': 0.0, 'p95': 0.10, 'count': 1}

daily = pt.get_daily_stats()
print("Daily PnL: $", daily['daily_pnl'])
print("Win rate: ", daily['win_rate'])
```

---

## Example 4: Query and Control the Circuit Breaker

```python
from trading.resilience.circuit_breaker import get_circuit_breaker, CircuitBreakerConfig

cb = get_circuit_breaker("scheduler_collapse")

print("State:         ", cb.state.value)      # "closed" | "open" | "half_open"
print("Failure count: ", cb.failure_count)
print("Success count: ", cb.success_count)

# Register a callback that fires when the circuit opens
cb.register_on_open(lambda: print("ALERT: Circuit opened — trading halted!"))

# Test the call wrapper
def fake_scheduler():
    raise RuntimeError("simulated failure")

ok, result = cb.call(fake_scheduler)
print("Call succeeded:", ok)   # False if circuit is OPEN
```

Check if the circuit is open and force-close it (e.g. after manual review):
```python
from trading.resilience.circuit_breaker import CircuitState

if cb.state == CircuitState.OPEN:
    print("Circuit is OPEN — manually reviewing situation")
    cb.manual_close()
    print("Circuit reset to CLOSED")
```

---

## Example 5: Compute Market Geometry

Compute the liquidity field, Christoffel symbols, and Gaussian curvature for a given price/time point.

```python
import time
import numpy as np
from trading.geometry.liquidity_field import LiquidityField
from trading.geometry.curvature import GaussianCurvature
from trading.geometry.connection import ChristoffelConnection

# Define some ICT zones
ob_zones  = [{"price": 1.0840, "strength": 0.8, "type": "bullish"}]
fvg_zones = [{"low": 1.0850, "high": 1.0858, "filled": False}]

field = LiquidityField()
phi = field.compute(
    price=1.0855,
    time=time.time(),
    ob_zones=ob_zones,
    fvg_zones=fvg_zones
)
print("ϕ(p,t) =", round(phi, 4))

# Gaussian curvature
K = GaussianCurvature().compute(phi, dp=0.001, dt=1.0)
if K > 0:
    regime_hint = "BASIN (mean-reversion likely)"
elif K < 0:
    regime_hint = "SADDLE (breakout likely)"
else:
    regime_hint = "FLAT (trend continuation)"

print("K =", round(K, 6), "→", regime_hint)
```

---

## Example 6: Direct Operator Scoring

Score a market state against all 18 ICT operators individually.

```python
import numpy as np
from trading.operators.operator_registry import OperatorRegistry

registry = OperatorRegistry()

# Build a minimal market state
market_state = {
    "price": 1.0855,
    "momentum": 0.0003,
    "spread": 0.00012,
    "volume": 1200,
    "volatility": 0.0008,
    "atr": 0.0025,
    "session": "london",
    "regime": "TRENDING",
    "sailing_alpha": 0.85,    # from regime detector
    "current_leg": 1,
    "max_legs": 5,
    "sailing_L0": 1.0,
    "swing_high": 1.0900,
    "swing_low": 1.0800,
    "bos_level": 1.0845
}

scores = registry.compute_all_scores(market_state)

for name, score in scores.items():
    print(f"  {name:12s}: {score:.4f}")
```

---

## Example 7: Inspect the Evidence Chain

```python
from trading.evidence.evidence_chain import EvidenceChain

chain = EvidenceChain()

# Get all signed records
records = chain.get_chain()
print(f"Chain length: {len(records)} records")

for record in records[-3:]:   # last 3 entries
    print("---")
    print("  timestamp: ", record.get("timestamp"))
    print("  decision:  ", record.get("decision"))
    print("  signature: ", record.get("signature", "")[:32], "...")
    print("  anchor:    ", record.get("anchor_hash", "")[:32], "...")

# Verify integrity
valid = chain.verify_chain()
print("\nChain integrity:", "VALID" if valid else "BROKEN")
```

---

## Example 8: Run a Regime Detection Pass

```python
import numpy as np
from trading.core.market_regime_detector import MarketRegimeDetector, MarketRegime

detector = MarketRegimeDetector()

# Provide recent close prices
closes = np.array([
    1.0850, 1.0855, 1.0860, 1.0868, 1.0872,
    1.0875, 1.0880, 1.0885, 1.0888, 1.0892,
    1.0895, 1.0900, 1.0905, 1.0910, 1.0915,
    1.0920, 1.0925, 1.0930, 1.0935, 1.0940
])

regime = detector.detect_regime(closes)
print("Regime:", regime.value)   # TRENDING | RANGING | HIGH_VOL | CRISIS

params = detector.get_regime_parameters(regime)
print("Trajectory count: ", params.trajectory_count)
print("Epsilon scale:    ", params.epsilon_scale)
print("Max position size:", params.max_position_size)
```

---

## Running All Examples

Save any example above to a `.py` file and run from the project root:

```bash
cd nvidia_chat
python my_example.py
```

Or run interactively:

```bash
python -i docs/examples/README.md   # won't work directly — paste into python REPL instead
python
>>> from trading.pipeline.orchestrator import PipelineOrchestrator
>>> ...
```
