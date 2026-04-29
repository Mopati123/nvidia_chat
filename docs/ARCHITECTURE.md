# Architecture Guide — ApexQuantumICT

## Overview

ApexQuantumICT treats financial markets as a curved Riemannian manifold and selects trades using the same variational principle that governs quantum field theory: the path of least action. Every decision passes through a 20-stage canonical pipeline and requires a cryptographic authorization token before execution.

The rootfile-first overlay makes that contract explicit without breaking the existing engine. Current modules stay in place, while canonical namespaces describe the architecture in first-order layers: state preparation, proposal generation, authorization, execution, evidence, validation, and API observation.

---

## Rootfile-First Overlay

The overlay is a map, not a hard migration. It preserves `trading.*`, `taep.*`, and `apps.*` imports while adding canonical packages that make the engine auditable by humans and validators.

```
data_core -> core.simulation -> core.orchestration -> core.execution -> tachyonic_chain
     |              |                    |                    |                 |
  prepare        propose             authorize               act             prove
```

### Canonical Layers

| Layer | Canonical namespace | Rule |
|-------|---------------------|------|
| State preparation | `data_core` | Normalize external data into internal market state; never execute trades |
| Proposal generation | `core.simulation` | Produce trajectories, geometry, operator scores, and strategy proposals; never mint tokens |
| Orchestration | `core.orchestration` | Apply constraints, choose paths, and remain the scheduler-owned source of execution authority |
| Authority | `core.authority` | Present one token facade over TAEP and trading scheduler tokens; expose `validate_token(...)` |
| Execution | `core.execution` | Gate shadow/live/broker actions with token validation and emit refusal evidence on denial |
| Evidence | `tachyonic_chain` | Export audit-chain and evidence primitives for accept/refuse paths |
| Interfaces | `backend_api` | Read state, issue user commands, and surface observations without bypassing authority |
| Validation | `tools` | Check metadata, import direction, token minting, token gating, and evidence boundaries |

### Token-Flow Authority

The authority invariant is intentionally simple: no shadow, live, or broker execution boundary should act without scheduler-issued permission. `core.authority.execution_token.ExecutionToken` is the canonical facade over existing TAEP and trading token implementations; `core.authority.token_validator.validate_token(...)` is the single execution-boundary validation entrypoint.

Schedulers remain the only components allowed to mint execution authority. Simulation and strategy modules are proposal generators only. If an execution boundary receives no token or an invalid token, it must refuse structurally and emit evidence rather than silently falling through.

### Overlay Migration Rule

The first pass favors adapters and registry metadata over file moves. This keeps the runtime stable while allowing validators to reason about the intended architecture. Hard migration is deferred until rootfile tests, deterministic shadow smoke tests, and broader package tests are green.

---

## State Space

The canonical state vector is:

```
x(t) = (q, p, k, π, σ, τ) ∈ A(t) ⊆ X
```

| Component | Type | Description |
|-----------|------|-------------|
| `q ∈ ℝⁿ` | geometric position | price, time, liquidity coordinates |
| `p ∈ ℝⁿ` | momentum | velocity, acceleration, spread |
| `k` | cryptographic key | 3-body chaos seeded entropy |
| `π` | policy/constraint | risk limits, session, regime |
| `σ ≥ 0` | statistical entropy | uncertainty measure |
| `τ` | ExecutionToken | cryptographic authorization proof |

`X \ A(t) = F(t)` — the forbidden region. No trade executes outside `A(t)`.

---

## Market Manifold (Riemannian Geometry)

Price movement is not Euclidean. The system models markets as a 2-dimensional Riemannian manifold with a conformal metric:

```
ds² = e^(2ϕ) (dp² + dt²)
```

### Liquidity Field ϕ(p, t)

The scalar field `ϕ` encodes market microstructure as curvature:

```
ϕ(p, t) = Σ [OB_weight × order_block_proximity]
          + Σ [FVG_weight × fair_value_gap_proximity]
          + session_decay(t)
          + spread_penalty
          + volume_density(p)
```

High `ϕ` = high resistance. Low `ϕ` = easy flow.

**File:** `trading/geometry/liquidity_field.py`

### Christoffel Symbols

Connection coefficients `Γⁱⱼₖ` encode how paths curve through the field:

```
Γ¹₁₁ = ∂ϕ/∂p,   Γ¹₁₂ = ∂ϕ/∂t
Γ²₁₁ = -∂ϕ/∂t,  Γ²₂₂ = ∂ϕ/∂t
```

**File:** `trading/geometry/connection.py`

### Gaussian Curvature K

```
K = -e^(-2ϕ) · Δϕ    (Laplacian of the liquidity field)
```

| K value | Regime | Trading Implication |
|---------|--------|---------------------|
| K > 0 | BASIN | Attractor — mean reversion |
| K ≈ 0 | FLAT | Trend continuation |
| K < 0 | SADDLE | Breakout, regime shift |

**File:** `trading/geometry/curvature.py`

### Geodesic Corrections

Trajectory seeds are corrected by geodesic deviation:

```
d²xⁱ/dλ² + Γⁱⱼₖ (dxʲ/dλ)(dxᵏ/dλ) = 0
```

**File:** `trading/geometry/geodesic.py`

---

## Hamiltonian (Total Energy)

```
H_total = H_geo + 0.5 · H_3body
```

### H_geo (Geometric Hamiltonian)

```
H_geo = T + V = p²/2m + ε · Σq²
```

A Hermitian matrix with kinetic energy `T` and harmonic potential `V`.

### H_3body (Chaos Hamiltonian)

Three-body gravitational ODE providing nonlinear coupling and high-entropy key seeding:

```
λ = lim_{t→∞} (1/t) log|δ(t)/δ₀| > 0    (positive Lyapunov exponent)
```

Symplectic Euler integration preserves phase space volume (Liouville's theorem).

**File:** `taep/hamiltonians/h_total.py`, `taep/chaos/three_body.py`

### Lindbladian Master Equation

State density matrix evolves as:

```
dρ/dt = -i[H, ρ] + Σₖ (Lₖ ρ Lₖ† - ½{Lₖ†Lₖ, ρ})
```

- **Unitary part** `-i[H,ρ]`: reversible price evolution
- **Lindblad operators** `Lₖ`: constraint-driven dissipation — inadmissible states are annihilated
- Maintains: `Tr(ρ)=1`, `ρ†=ρ`, eigenvalues ≥ 0

**File:** `taep/core/master_equation.py`

---

## Path Integral (Trajectory Selection)

```
S[γ] = ∫ L dt = ∫ (T - V) dt      (action functional)
P[γ] ∝ exp(-S[γ]/ℏ)               (Wick-rotated probability weight)
γ* = argmin S[γ]                   (classical least-action path)
```

### RK4 Integration

N candidate trajectories are generated via 4th-order Runge-Kutta, each seeded with geodesic curvature corrections. The effective Planck constant `ℏ` (epsilon) is calibrated via bisection so the Effective Sample Size (ESS) ≈ 0.5.

### Action Decomposition

```
S[γ] = w_L · S_L + w_T · S_T + w_E · S_E + w_R · S_R
```

| Component | Weight | Description |
|-----------|--------|-------------|
| `S_L` | `w_L` | Liquidity action (field resistance) |
| `S_T` | `w_T` | Time action (session timing) |
| `S_E` | `w_E` | Entry action (price level quality) |
| `S_R` | `w_R` | Risk action (stop/target geometry) |

**File:** `trading/path_integral/trajectory_generator.py`

### Order-Book Microstructure Overlay

The order-book overlay adds an analytics-only Stage 2.5 after state construction when `raw_data["order_book"]` is present. It does not open WebSockets, poll brokers, mint tokens, place orders, or bypass scheduler authority. It converts normalized depth snapshots into HFT-style observables and stores them on `PipelineContext.order_book`, `PipelineContext.hft_signals`, and `market_state["hft_signals"]`.

```
Raw depth snapshot -> OrderBookEngine -> O19-O25 signals -> optional S_HFT cost
```

| Signal | Meaning | Execution behavior |
|--------|---------|--------------------|
| `depth_imbalance` | Bid/ask depth asymmetry | Scoring only |
| `layering_score` | Uniform resting-size layering risk | Scoring only |
| `enhanced_microprice` | Depth-weighted fair price | Scoring only |
| `pressure_ratio` | Bid/ask pressure continuation | Scoring only |
| `iceberg_probability` | Refill-after-drain likelihood | Scoring only |
| `book_inversion` | Crossed-book circuit-breaker observable | Penalizes action; never executes |
| `cumulative_delta` | Time-integrated signed depth change | Scoring only |

When HFT signals exist, the action functional becomes:

```
S[γ] = w_L*S_L + w_T*S_T + w_E*S_E + w_R*S_R + w_HFT*S_HFT
```

`S_HFT` rewards alignment between the proposed path and book pressure, and heavily penalizes crossed/inverted books. This improves entry timing and trajectory filtering while preserving the rootfile invariant that only scheduler-issued tokens can authorize execution.

**Files:** `trading/microstructure/order_book.py`, `trading/action/upgraded_components.py`, `core/simulation/order_book.py`

---

## 25-Operator Market Hamiltonian

```
H_market = Σ_{k=1}^{25} αₖ · Oₖ
```

O1-O18 remain the legacy ICT/SMC operator contract. O19-O25 are analytics-only order-book observables; they enrich scoring and evidence but do not authorize execution.

### Potential Operators (O1–O7)

| # | Operator | Formula | ICT Concept |
|---|----------|---------|-------------|
| O1 | T(p;σ) | p²/(2m·σ) | Momentum / kinetic energy |
| O2 | V_LP(x) | −κ · ∫V(x′)e^(−\|x−x′\|/λ) dx′ | Liquidity pool attraction |
| O3 | V_OB(x) | (body/range) · log(vol/vol_mean) if body>70% | Order block footprint |
| O4 | V_FVG(x) | gap_size / ATR | Fair value gap imbalance |
| O5 | V_macro(t) | session_weight · exp(−\|t−peak\|/τ) | Kill zone time-decay |
| O6 | V_PD(x) | (price − midline) / (H − L) | Premium/discount delivery |
| O7 | V_regime | MarketRegimeDetector continuous score | BOS/CHOCH regime |

### Projector Operators (O8–O17)

| # | Operator | Formula | ICT Concept |
|---|----------|---------|-------------|
| O8 | Π_session | 1 if trading hours, 0 otherwise | Session gate |
| O9 | Π_risk | 1 if exposure ≤ limit, 0 otherwise | Risk exposure gate |
| O10 | L(n) | L₀ · α^(n-1), α from regime | Sailing lane multi-leg decay |
| O11 | S_liq | reversal_momentum if sweep+close_inside | Liquidity sweep reversal |
| O12 | D(x,t) | body / ATR if body > 2.5×ATR | Impulsive displacement |
| O13 | BB(x) | proximity if former support after BOS | Breaker block |
| O14 | MB(x) | 1 − (dist / ATR) | Mitigation block return |
| O15 | OTE(x) | 1 if Fib 0.62–0.79 from last BOS | Optimal trade entry |
| O16 | J(x,t) | reversal_speed if early session false move | Judas swing |
| O17 | A(x,t) | Wyckoff: range compression + volume dry-up | Accumulation/distribution |

### Measurement Operator (O18)

```
⟨ψ|H|ψ⟩ = ψᵀ · H_market · ψ    (full quantum readout)
```

### Order-Book Operators (O19-O25)

| # | Operator | Formula | Microstructure Concept |
|---|----------|---------|------------------------|
| O19 | `depth_imbalance` | `(bid_depth - ask_depth) / total_depth` | Depth pressure |
| O20 | `volume_layering` | low coefficient of variation across top levels | Layering risk |
| O21 | `enhanced_microprice` | depth-weighted fair price | Entry refinement |
| O22 | `bid_ask_pressure` | bid pressure / ask pressure | Pressure continuation |
| O23 | `iceberg_detection` | drain-and-refill probability | Hidden liquidity |
| O24 | `cumulative_delta_pressure` | cumulative signed depth change | Flow persistence |
| O25 | `book_inversion` | crossed-book indicator | Circuit-breaker observable |

**File:** `trading/operators/operator_registry.py`

---

## 20-Stage Canonical Pipeline

```
RAW MARKET DATA (MT5 / Deriv / TradingView)
        ↓
┌──────────────────────────────────────────────────────────────┐
│  STAGE  │  NAME                    │  MODULE                │
├─────────┼──────────────────────────┼────────────────────────┤
│  1      │  DATA_INGESTION          │  pipeline/orchestrator │
│  2      │  STATE_CONSTRUCTION      │  microstructure/       │
│  3      │  ICT_EXTRACTION          │  operators/            │
│  4      │  GEOMETRY_COMPUTATION    │  geometry/             │
│  5      │  TRAJECTORY_GENERATION   │  path_integral/        │
│  6      │  RAMANUJAN_COMPRESSION   │  path_integral/        │
│  7      │  ADMISSIBILITY_FILTERING │  taep/constraints/     │
│  8      │  ACTION_EVALUATION       │  trading/action/       │
│  9      │  PATH_INTEGRAL           │  path_integral/        │
│  10     │  INTERFERENCE_SELECTION  │  path_integral/        │
│  11     │  PATH_SELECTION          │  pipeline/orchestrator │
│  12     │  PROPOSAL_GENERATION     │  pipeline/orchestrator │
│  13     │  ADMISSIBILITY_CHECK     │  risk/risk_manager     │
│  14     │  ENTROPY_GATE            │  pipeline/orchestrator │
│  15     │  SCHEDULER_COLLAPSE ←CB  │  taep/scheduler/       │
│  16     │  EXECUTION               │  brokers/              │
│  17     │  RECONCILIATION ←PnLDiv  │  risk/pnl_tracker      │
│  18     │  EVIDENCE_EMISSION       │  evidence/             │
│  19     │  WEIGHT_UPDATE           │  rl/scheduler_agent    │
│  20     │  COMPLETED               │  pipeline/orchestrator │
└──────────────────────────────────────────────────────────────┘
        ↓
CRYPTOGRAPHIC AUDIT CHAIN (Ed25519 + Merkle Tree)
```

### Stage Details

| Stage | What it does |
|-------|-------------|
| 1. DATA_INGESTION | Normalize raw OHLCV/tick data from broker; validate completeness |
| 2. STATE_CONSTRUCTION | Build market microstructure: OFI, microprice, order flow velocity |
| 3. ICT_EXTRACTION | Identify order blocks, FVGs, BOS/CHOCH, liquidity zones, session |
| 4. GEOMETRY_COMPUTATION | Compute ϕ(p,t) → metric g_ij → Γⁱⱼₖ → curvature K → regime |
| 5. TRAJECTORY_GENERATION | RK4 integration → N candidate paths with geodesic-seeded initial conditions |
| 6. RAMANUJAN_COMPRESSION | Cluster paths into behavioral families; reduce redundancy |
| 7. ADMISSIBILITY_FILTERING | Π_total gate: discard paths violating constraints |
| 8. ACTION_EVALUATION | Compute S[γ] = w_L·S_L + w_T·S_T + w_E·S_E + w_R·S_R (+ optional S_HFT) for each path |
| 9. PATH_INTEGRAL | Weight each path: P ∝ exp(−S/ℏ); calibrate ℏ for ESS≈0.5 |
| 10. INTERFERENCE_SELECTION | Destructive interference cancels high-action paths |
| 11. PATH_SELECTION | γ* = argmax weight = argmin action |
| 12. PROPOSAL_GENERATION | Extract (direction, entry, stop, target, size, predicted_pnl) from γ* |
| 13. ADMISSIBILITY_CHECK | Final risk gate: check_all_limits() from risk manager |
| 14. ENTROPY_GATE | ΔS < threshold: reject if trajectory variance too high |
| 15. SCHEDULER_COLLAPSE | Issue ExecutionToken or REFUSE; **circuit breaker** wraps this call |
| 16. EXECUTION | Submit to shadow/paper/live broker via ExecutionToken |
| 17. RECONCILIATION | PnL divergence: \|predicted − realized\| / max(\|predicted\|, 1) |
| 18. EVIDENCE_EMISSION | Ed25519 sign + Merkle-chain the evidence record |
| 19. WEIGHT_UPDATE | PPO reward + backward law: w_new ← Π_simplex(w_old + η·J) |
| 20. COMPLETED | Update state, log metrics, prepare for next cycle |

---

## Production Hardening (T3-A)

### Circuit Breaker — Stage 15

State machine: `CLOSED → OPEN → HALF_OPEN`

```
failure_threshold  = 10   (consecutive failures to open)
success_threshold  = 3    (consecutive successes to close from HALF_OPEN)
timeout_seconds    = 30   (auto-transition OPEN → HALF_OPEN after 30s)
```

When the circuit opens, `risk_manager.trigger_kill_switch("circuit_breaker_open")` fires automatically.

**File:** `trading/resilience/circuit_breaker.py`

### PnL Divergence Detection — Stage 17

```
pnl_divergence = |predicted_pnl − realized_pnl| / max(|predicted_pnl|, 1.0)
```

If `pnl_divergence > 0.15` (15%):
- Logs a warning
- Calls `scheduler.update_action_weights(pnl=−divergence×10, ...)` — weight penalty
- Records in a rolling 100-trade histogram (`deque(maxlen=100)`)

**File:** `trading/risk/pnl_tracker.py` (`record_execution_error`, `get_divergence_stats`)

---

## Acceleration Tiers

The hot-path computations (trajectory generation, operator scoring) run at the best available speed tier:

```
Mojo binary          → 100–1000× speedup    trading/accelerated/mojo/
Cython extensions    → 10–100× speedup      trading/accelerated/_path_integral.pyx
Numba JIT            → 2–10× speedup        (automatic fallback)
Pure NumPy           → 1× baseline          (always available)
```

The bridge (`trading/accelerated/mojo_bridge.py`) auto-detects which tier is available and dispatches accordingly.

---

## Multi-Layer Architecture

```
PHYSICS CORE (taep/)
├── Hamiltonians: H_geo, H_3body, H_total
├── Master equation: Lindbladian dρ/dt
├── State: (q, p, k, π, σ, τ) ∈ A(t)
├── Chaos: 3-body → Lyapunov → entropy
├── Constraints: admissibility projectors Π
├── Scheduler: collapse authority + ExecutionToken
└── Evidence: Ed25519 signatures + Merkle tree

TRADING ENGINE (trading/)
├── Geometry: ϕ → metric → Γ → K → regime
├── Path Integral: RK4 → action → γ* selection
├── Operators: 25-operator ICT + order-book registry
├── Microstructure: OFI, microprice, flow field, order-book depth signals
├── Memory: 128-dim FAISS embeddings + RAG bias
├── RL: PPO agent (166-dim state) → weight adaptation
├── Regime: ADX+Vol detector → parameter wiring
├── Risk: Kelly sizing, hard stops, PnL tracker
├── Resilience: circuit breakers, state recovery
└── Brokers: MT5, Deriv WebSocket, TradingView

ACCELERATION (trading/accelerated/)
├── Mojo:   trajectory_engine.mojo
├── Cython: _path_integral.pyx, _operators.pyx
├── Numba:  JIT fallback
└── NumPy:  pure Python fallback

INTERFACE
├── Telegram bot (Falcon / Nemotron / Qwen via NVIDIA API)
├── FastAPI dashboard (/metrics, /kill)
├── Paper trading loop
└── Shadow trading loop (zero capital)
```
