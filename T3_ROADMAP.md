# T3 Enhancement Roadmap — ApexQuantumICT
## Post-T2 Strategic Initiatives (2026-04-22 onward)

---

## Executive Summary

T1-C and T2-H are complete. All 20-stage pipeline stages are implemented, verified, and deployed. **T3 focuses on:**
1. **Production hardening** — eliminate single points of failure, implement recovery protocols
2. **Performance optimization** — profile hot paths, GPU acceleration, distributed execution
3. **Advanced observability** — comprehensive metrics, state recovery, audit trail integrity
4. **Live trading readiness** — broker integration robustness, slippage modeling, partial fills

---

## Strategic Phases

### PHASE T3-A: Production Hardening & Resilience

#### T3-A1: Circuit Breakers & Automatic State Recovery

**Problem:** System loss of signal, network partition, or cascade failure can leave risk_manager in inconsistent state.

**Solution:** Add fault injection handlers at each stage boundary.

**Files to modify:**
- `trading/pipeline/orchestrator.py` — add circuit breaker at stage 15 (collapse)
- `trading/risk/risk_manager.py` — add `recover_from_checkpoint()` method
- `taep/scheduler/scheduler.py` — persist before/after collapse state

**Tasks:**
1. Implement `CircuitBreakerState` enum: `CLOSED` (normal) → `OPEN` (failed) → `HALF_OPEN` (recovery) → `CLOSED`
2. In orchestrator stage 15, wrap `scheduler_collapse()` in circuit breaker
3. Add exponential backoff: T_retry = T_min × (T_multiplier ^ failures)
4. On persistent failure (N > 10 retries): trigger kill_switch automatically
5. Add `Checkpoint` dataclass (timestamp, state_hash, evidence_hash) persisted to `trading_data/state/checkpoints/`
6. On recovery, validate checkpoint hash against current state; if mismatch → forced reconciliation

**Verification:**
```python
cb = CircuitBreaker()
for i in range(15):
    result = cb.call(failing_fn)  # fails
assert cb.state == CircuitBreakerState.OPEN
# recover after cooldown:
time.sleep(5)
result = cb.call(failing_fn)  # retries
assert cb.state == CircuitBreakerState.HALF_OPEN
```

---

#### T3-A2: State Reconciliation & Divergence Detection

**Problem:** Predicted trajectory vs actual execution can diverge (slippage, partial fills, market impact). System must detect and correct.

**Solution:** After each trade close, compute |predicted_pnl - actual_pnl| and flag divergence.

**Files to modify:**
- `trading/evidence/evidence_chain.py` — add reconciliation evidence
- `trading/risk/pnl_tracker.py` — add `estimate_execution_error()` method
- `trading/pipeline/orchestrator.py` — stage 17 (reconciliation) hardening

**Tasks:**
1. Store predicted trajectory energy S[γ*] in TradeRecord
2. After trade close: divergence = |S[γ*] - realized_pnl| / max(|S[γ*]|, 1.0)
3. If divergence > 0.15 (15%):
   - Log as anomaly (evidence chain)
   - Trigger weight adjustment penalty (reduce w_L, w_E by -0.05)
   - Alert dashboard with CAUTION badge
4. Maintain rolling divergence histogram: `self.divergence_history = collections.deque(maxlen=1000)`
5. Add `/metrics` endpoint field: `"execution_error_pct": divergence_rolling_mean()`

**Verification:**
```python
tracker = PnLTracker()
record = TradeRecord(predicted_energy=50.0)
tracker.record_trade(record)
error = tracker.estimate_execution_error(record, realized_pnl=55.0)
assert 0.09 < error < 0.11  # ~10% divergence
assert tracker._anomaly_count > 0  # logged
```

---

### PHASE T3-B: GPU Acceleration

#### T3-B1: CUDA Trajectory Batching

**Problem:** Generating 100-1000 trajectories sequentially takes O(N × steps) CPU time.

**Solution:** Batch trajectory ODE integration on GPU via CuPy or Numba CUDA.

**Files to create:**
- `trading/accelerated/_trajectories_gpu.py` — CUDA kernel wrapper

**Design:**
```python
@cuda.jit
def rk4_batch_kernel(qs, ps, ks, energies, steps, dt):
    """Parallel RK4 for all trajectories simultaneously."""
    idx = cuda.grid(1)
    if idx >= len(qs):
        return
    # Each thread integrates one trajectory
    for step in range(steps):
        k1, m1 = compute_derivatives(qs[idx], ps[idx], dt)
        # ... RK4 stages ...
```

**Tasks:**
1. Convert trajectory array to CuPy arrays (GPU memory)
2. Launch kernel with grid=(num_trajectories // 256 + 1), block=(256,)
3. Collect results back to CPU
4. Measure speedup: target 50-200x on RTX 4090

**Target speedup:** 100 trajectories: 500ms → 5ms

---

#### T3-B2: Operator Scoring on GPU

**Problem:** 18-operator scoring for each trajectory is 18 memory lookups + 18 floating-point ops; scales poorly.

**Solution:** Vectorize operator scoring across all trajectories at once.

**Files to modify:**
- `trading/operators/operator_registry.py` — add `compute_all_scores_gpu()` method

**Tasks:**
1. Pre-allocate GPU arrays for all trajectories' OHLCV data
2. Call 18 GPU kernels (one per operator) in batch
3. Collect scores into (N_trajectories, 18) matrix
4. Return to CPU

**Target speedup:** 20-50x for 100 trajectories

---

### PHASE T3-C: Advanced Observability

#### T3-C1: Comprehensive Metrics Pipeline

**Files to create/modify:**
- `trading/observability/metrics.py` — new prometheus-style metrics collector
- `trading/dashboard/app.py` — add `/prometheus` endpoint

**Metrics to expose:**
1. Pipeline stage timings (histograms)
2. Trajectory quality metrics (mean energy, entropy)
3. Weight adaptation history (per component)
4. Win rate, Sharpe, max drawdown (rolling)
5. Risk check failure rate
6. Divergence (predicted vs actual)
7. Broker execution latency
8. Circuit breaker state transitions

**Tasks:**
1. Create `MetricsCollector` singleton
2. Add timing instrumentation to each pipeline stage
3. Export `/prometheus` endpoint as Prometheus-format metrics
4. Connect Grafana dashboard for visualization

**Example metrics:**
```
# HELP apex_pipeline_stage_duration_seconds Latency per stage
# TYPE apex_pipeline_stage_duration_seconds histogram
apex_pipeline_stage_duration_seconds_bucket{stage="geometry_computation",le="0.01"} 1234
apex_pipeline_stage_duration_seconds_bucket{stage="action_evaluation",le="0.05"} 567
...
```

---

#### T3-C2: Merkle Audit Trail Checkpointing

**Problem:** Evidence chain grows unbounded; expensive to validate.

**Solution:** Checkpoint evidence every 1000 trades; new merkle tree references checkpoint.

**Files to modify:**
- `trading/evidence/evidence_chain.py` — add checkpoint logic
- `taep/audit/` — new checkpoint manager

**Tasks:**
1. Every 1000 trades: compute merkle root of last 1000 evidences
2. Save checkpoint: `(timestamp, trade_range_start, trade_range_end, merkle_root, signature)`
3. New checkpoint references prior checkpoint's root → chain of checkpoints
4. On-demand validation: verify 1000-evidence merkle, then checkpoint sig

**Benefit:** O(log N) audit trail validation instead of O(N)

---

### PHASE T3-D: Live Trading Infrastructure

#### T3-D1: Execution Slippage Modeling

**Problem:** Predicted prices assume atomic fills; actual fills suffer slippage from liquidity + market impact.

**Solution:** Learn slippage function from historical divergence data.

**Files to create:**
- `trading/brokers/slippage_model.py` — slippage estimator

**Design:**
```python
class SlippageModel:
    def estimate(self, symbol: str, size: float, spread: float, session: str) -> float:
        """
        Estimate expected slippage (in pips).
        Based on: size (execution impact) + spread (market tightness) + session (liquidity)
        """
        return base_slip + a * log(size) + b * spread + c * session_factor
    
    def update(self, realized_divergence: float) -> None:
        """Backward learning: adapt model based on divergence."""
        self.params += eta * gradient(realized_divergence)
```

**Tasks:**
1. Collect historical slippage: (symbol, size, spread, session) → actual_divergence
2. Fit linear model: slippage = β₀ + β₁·log(size) + β₂·spread + β₃·session_factor
3. In trajectory generation: adjust predicted entry/exit by ±slippage estimate
4. After trade close: update slippage model with realized error

**Verification:**
```python
model = SlippageModel()
model.train(historical_data)  # fit from past 1000 trades
predicted_slip = model.estimate("EURUSD", size=0.1, spread=0.0002, session="LONDON")
assert 0.0001 < predicted_slip < 0.001  # reasonable range
```

---

#### T3-D2: Partial Fill & Queue Rejection Handling

**Problem:** Broker may reject order (insufficient margin) or partially fill (liquidity exhaustion).

**Solution:** Implement fallback ordering strategy.

**Files to modify:**
- `trading/brokers/signal_router.py` — add fallback logic
- `trading/paper_trading_loop.py` — handle partial fills

**Tasks:**
1. On order rejection: 
   - Reduce size by 50% and resubmit
   - If rejected again: log as anomaly, do not retry
2. On partial fill:
   - Track unfilled quantity
   - Attempt resubmit after 500ms with remaining size
   - Cancel remaining after 3 failed resubmits
3. Emit evidence for each resubmit attempt + outcome

**State machine:**
```
PENDING → PARTIALLY_FILLED → PENDING (retry) → REJECTED or FILLED
```

---

### PHASE T3-E: Distributed Architecture

#### T3-E1: Multi-Process Backtest Runner

**Problem:** Single-threaded backtesting on 10 years of data is slow (O(years × 1440 ticks/day)).

**Solution:** Parallelize backtest across multiple symbol-batches using ProcessPoolExecutor.

**Files to create:**
- `trading/backtesting/distributed_backtest.py`

**Design:**
```python
from concurrent.futures import ProcessPoolExecutor

def run_backtest_batch(symbols: List[str], date_range: Tuple[date, date]) -> Dict:
    """Single process: run backtest on symbol batch."""
    orchestrator = PipelineOrchestrator()
    trades = []
    for date in date_range:
        for tick in load_ticks(symbols, date):
            result = orchestrator.execute(tick)
            if result.trade:
                trades.append(result.trade)
    return compute_stats(trades)

def distributed_backtest(all_symbols: List[str], date_range: Tuple[date, date], n_workers: int = 4):
    """Launch backtest on multiple processes."""
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        batches = chunk(all_symbols, len(all_symbols) // n_workers)
        futures = [executor.submit(run_backtest_batch, batch, date_range) for batch in batches]
        results = [f.result() for f in futures]
    return aggregate_results(results)
```

**Target:** 4x speedup on 4-core CPU

---

### PHASE T3-F: Advanced RL Features

#### T3-F1: Ensemble Action Selection

**Problem:** Single PPO agent can be overconfident; single trajectory selection is brittle.

**Solution:** Train 3 independent PPO agents; use voting/averaging for action selection.

**Files to modify:**
- `trading/rl/scheduler_agent.py` → create ensemble wrapper

**Design:**
```python
class PPOEnsemble:
    def __init__(self, n_agents: int = 3):
        self.agents = [PPOSchedulerAgent() for _ in range(n_agents)]
    
    def select_action(self, state: np.ndarray):
        """Query all agents; select action via majority vote."""
        actions = []
        for agent in self.agents:
            action, log_prob, value = agent.select_action(state)
            actions.append(action)
        # majority vote, or random if tie
        consensus_action = np.bincount(actions).argmax()
        return consensus_action, highest_value
    
    def update(self, *args, **kwargs):
        """Update all agents in parallel."""
        for agent in self.agents:
            agent.update(*args, **kwargs)
```

**Benefits:**
- Reduced overfitting (ensemble diversity)
- Increased robustness to outlier trajectories
- Can detect agent disagreement → caution signal

---

#### T3-F2: Curiosity-Driven Exploration

**Problem:** PPO agent optimizes for PnL only; may miss regime transitions or novel market structures.

**Solution:** Add intrinsic curiosity reward (prediction error) to extrinsic PnL reward.

**Design:**
```python
class CuriosityBonus:
    def __init__(self):
        self.forward_model = ForwardModel(input_dim=166, output_dim=128)  # state → next_embedding
        self.optimizer = optim.Adam(self.forward_model.parameters())
    
    def compute_curiosity(self, state: np.ndarray, next_state: np.ndarray) -> float:
        """Intrinsic reward = prediction error."""
        pred = self.forward_model(state)
        true = forward_encode(next_state)
        return torch.nn.functional.mse_loss(pred, true)
    
    def update(self, state, next_state):
        """Train forward model."""
        loss = self.compute_curiosity(state, next_state)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

class PPOWithCuriosity:
    def compute_reward(self, pnl: float, curiosity: float) -> float:
        return pnl + alpha * curiosity  # alpha ≈ 0.01
```

---

## Implementation Sequence (T3)

```
T3-A: Production Hardening
  ├─ T3-A1: Circuit breakers & recovery (3 days)
  └─ T3-A2: State reconciliation & divergence detection (2 days)

T3-B: GPU Acceleration
  ├─ T3-B1: CUDA trajectory batching (5 days, optional CuPy/Numba)
  └─ T3-B2: Operator scoring on GPU (3 days)

T3-C: Observability
  ├─ T3-C1: Prometheus metrics + Grafana (2 days)
  └─ T3-C2: Merkle audit checkpointing (2 days)

T3-D: Live Trading Infrastructure
  ├─ T3-D1: Slippage modeling (2 days)
  └─ T3-D2: Partial fill handling (2 days)

T3-E: Distributed Backtest (1 day)

T3-F: Advanced RL (optional, 2-3 days)
  ├─ T3-F1: Ensemble action selection
  └─ T3-F2: Curiosity-driven exploration
```

**Recommended priority order:**
1. **T3-A (Production Hardening)** — Ship first, most critical for live trading
2. **T3-C (Observability)** — Monitor dashboard + detect failures
3. **T3-D1 (Slippage Modeling)** — Realistic PnL predictions
4. **T3-B (GPU Acceleration)** — Speed up if needed for live latency targets
5. **T3-D2, T3-E, T3-F** — Nice-to-have, iterate as needed

---

## Success Criteria

| Phase | Success Criterion |
|-------|------------------|
| T3-A1 | Circuit breaker triggers, recovers, zero trades missed during downtime |
| T3-A2 | Divergence flag rate < 5%, weight adaptation converges within 50 trades |
| T3-B1 | GPU trajectory generation: 100 trajectories < 10ms (vs 200ms CPU) |
| T3-B2 | Batch operator scoring: 10× speedup |
| T3-C1 | All 20 pipeline stages instrumented; Prometheus endpoint live |
| T3-C2 | Checkpoint every 1000 trades; validation latency < 100ms |
| T3-D1 | Slippage model R² > 0.7 on holdout test set |
| T3-D2 | Partial fill recovery success rate > 95% |
| T3-E | 4-process backtest: 4× speedup (measured) |
| T3-F1 | Ensemble Sharpe > single-agent Sharpe by 5-10% |
| T3-F2 | Curiosity bonus detects regime shift 2-5 trades before divergence flag |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| GPU memory pressure | Batch size adaptive; CPU fallback if OOM |
| Ensemble action disagreement | Log dissent; reduce position size by 50% |
| Checkpoint verification failure | Rollback to prior checkpoint; emit alert |
| Slippage model overfitting | Regularization (L2) + separate test set |
| Distributed backtest race conditions | Use file-based coordination (atomic writes) |

---

## Deliverables

- 6 new modules (circuit_breaker, state_reconciliation, metrics, slippage, distributed_backtest, gpu_trajectories)
- Updated orchestrator stage implementations
- Comprehensive test suite (unit + integration)
- Prometheus metrics + Grafana dashboard JSON
- Updated audit trail with checkpoint references
- Performance profiling report (before/after GPU)
- Live trading readiness checklist

