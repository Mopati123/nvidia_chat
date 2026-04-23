# ApexQuantumICT — Quantum-Physics Algorithmic Trading System

A production-grade trading bot that models financial markets as curved physical space and finds optimal trades using Feynman's path integral — the same mathematics that governs how particles move through quantum fields.

Every trade decision is authorized by a cryptographic governance protocol, signed with Ed25519, and stored in an immutable Merkle-chained audit trail.

---

## What It Does

Instead of simple indicators (RSI, MACD), this system:

1. **Models price movement as geodesics through curved spacetime** — the liquidity field `ϕ(p,t)` encodes order blocks, fair value gaps, and session timing as curvature; price follows the path of least resistance
2. **Generates N candidate trajectories via RK4 path integration** — each seeded with geodesic curvature corrections, integrated with live Christoffel symbol acceleration
3. **Scores every trajectory against 18 ICT/SMC quantum operators** — order blocks, FVGs, liquidity sweeps, OTE fibonacci, Judas swings, Wyckoff accumulation, and 12 more
4. **Selects the minimum-action path** — the trajectory with lowest `S[γ] = w_L·S_L + w_T·S_T + w_E·S_E + w_R·S_R`
5. **Requires cryptographic authorization to execute** — the scheduler issues a signed `ExecutionToken` or refuses; no token = no trade
6. **Learns from every outcome** — PPO reinforcement learning agent + backward weight adaptation continuously improve trajectory selection

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Architecture Guide](docs/ARCHITECTURE.md) | System design — physics core, 20-stage pipeline, manifold geometry |
| [API Reference](docs/API.md) | Complete class and method reference for all modules |
| [Tutorials](docs/TUTORIAL.md) | Step-by-step guides: paper trading, dashboard, Telegram bot, brokers |
| [Examples](docs/examples/README.md) | Working Python code snippets |

---

## Architecture

```
RAW MARKET DATA (MT5 / Deriv / TradingView)
        ↓
┌─────────────────────────────────────────┐
│         20-STAGE PIPELINE               │
│  1. Data Ingestion                      │
│  2. State Construction (microstructure) │
│  3. ICT Extraction (OB, FVG, BOS)       │
│  4. Geometry (ϕ → Γ → curvature K)      │
│  5. Trajectory Generation (RK4)         │
│  6. Ramanujan Compression               │
│  7. Admissibility Filtering             │
│  8. Action Evaluation (S[γ])            │
│  9. Path Integral Weighting             │
│ 10. Interference Selection              │
│ 11. Path Selection (γ* = argmin S)      │
│ 12. Proposal Generation                 │
│ 13. Admissibility Check (risk gate)     │
│ 14. Entropy Gate (ΔS < threshold)       │
│ 15. Scheduler Collapse ← CIRCUIT BREAKER│
│ 16. Execution (paper / live)            │
│ 17. Reconciliation ← PnL DIVERGENCE    │
│ 18. Evidence Emission (Ed25519+Merkle)  │
│ 19. Weight Update (PPO + backward law)  │
│ 20. Completed                           │
└─────────────────────────────────────────┘
        ↓
CRYPTOGRAPHIC AUDIT CHAIN
```

---

## Repository Structure

```
nvidia_chat/
├── trading/
│   ├── pipeline/orchestrator.py      ← 20-stage pipeline master
│   ├── kernel/
│   │   ├── apex_engine.py            ← Wavefunction collapse engine
│   │   ├── scheduler.py              ← Collapse authority + HMAC tokens
│   │   └── H_constraints.py          ← Constraint projectors
│   ├── geometry/                     ← Riemannian market manifold
│   │   ├── liquidity_field.py        ← ϕ(p,t) field computation
│   │   ├── connection.py             ← Christoffel symbols Γ^i_jk
│   │   ├── curvature.py              ← Gaussian curvature K
│   │   ├── metric.py                 ← Conformal metric g_ij
│   │   └── geodesic.py               ← Geodesic path corrections
│   ├── path_integral/
│   │   └── trajectory_generator.py  ← RK4 integration + ESS calibration
│   ├── operators/
│   │   └── operator_registry.py     ← All 18 ICT operators (exact math)
│   ├── risk/
│   │   ├── risk_manager.py           ← Hard stops, kill switch, regime limits
│   │   └── pnl_tracker.py           ← Daily PnL + execution error histogram
│   ├── resilience/
│   │   ├── circuit_breaker.py        ← CLOSED→OPEN→HALF_OPEN state machine
│   │   └── state_recovery.py         ← Crash recovery + snapshot persistence
│   ├── evidence/
│   │   └── evidence_chain.py         ← Ed25519 signatures + Merkle tree
│   ├── memory/
│   │   └── vector_store.py           ← FAISS 128-dim cosine similarity
│   ├── rl/
│   │   ├── scheduler_agent.py        ← PPO agent (166-dim state space)
│   │   └── ppo_paper_hook.py         ← Paper trade → RL reward feedback
│   ├── brokers/
│   │   ├── mt5_broker.py             ← MetaTrader 5
│   │   ├── deriv_broker.py           ← Deriv WebSocket
│   │   ├── tradingview_connector.py  ← TradingView webhooks
│   │   └── async_tick_loop.py        ← Asyncio producer-consumer tick ingestion
│   ├── dashboard/
│   │   └── app.py                    ← FastAPI live dashboard (/metrics, /kill)
│   ├── core/
│   │   └── market_regime_detector.py ← TRENDING/RANGING/HIGH_VOL/CRISIS
│   ├── shadow/                        ← Paper trading (zero capital)
│   ├── microstructure/                ← OFI, microprice, flow field
│   ├── agents/                        ← Multi-agent voting system
│   └── accelerated/                   ← Mojo / Cython / Numba speed tiers
│       ├── _path_integral.pyx
│       ├── _operators.pyx
│       └── mojo/core/trajectory_engine.mojo
├── taep/                              ← Physics core
│   ├── hamiltonians/                  ← H_geo, H_3body, H_total
│   ├── chaos/three_body.py            ← Lyapunov entropy source
│   ├── core/master_equation.py        ← Lindbladian dρ/dt
│   ├── scheduler/scheduler.py         ← ExecutionToken authority
│   └── constraints/                   ← Admissibility projectors Π
├── tests/                             ← Organised unit + integration tests
├── test_t2_integration.py             ← T2 enhancements (all passing)
├── test_t3a_integration.py            ← T3-A production hardening (all passing)
├── T3_ROADMAP.md                      ← Strategic roadmap (T3-A through T3-F)
├── start_paper_trading.py             ← Launch paper trading loop
├── telegram_bot_full.py               ← Telegram control interface
└── requirements.txt
```

---

## Quick Start

```bash
git clone https://github.com/Mopati123/nvidia_chat.git
cd nvidia_chat
pip install -r requirements.txt
```

### Run Paper Trading

```bash
python start_paper_trading.py
```

### Run the Dashboard

```bash
uvicorn trading.dashboard.app:app --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080` — live PnL, regime, circuit breaker state, kill switch.

### Run Integration Tests

```bash
# T2 enhancements (geodesic, FAISS, PPO, async, dashboard, Mojo)
python -m pytest test_t2_integration.py -v

# T3-A production hardening (circuit breaker, PnL divergence)
python -m pytest test_t3a_integration.py -v

# Full test suite
python -m pytest tests/ -v
```

---

## Environment Variables

```bash
# Signing key (Ed25519 private key PEM — never commit this)
export APEX_SIGNING_KEY="-----BEGIN PRIVATE KEY-----..."

# Broker credentials
export MT5_LOGIN="your_login"
export MT5_PASSWORD="your_password"
export MT5_SERVER="your_broker_server"

export DERIV_APP_ID="your_app_id"
export DERIV_API_TOKEN="your_token"

# NVIDIA API (for Telegram bot AI models)
export NVIDIA_API_KEY="your_nvidia_key"

# Telegram
export TELEGRAM_BOT_TOKEN="your_bot_token"

# Risk limits
export MAX_RISK_PER_TRADE="0.02"
export DAILY_LOSS_LIMIT="500"
```

---

## The 18 ICT Operators

| # | Operator | Physics Role | ICT Concept |
|---|----------|-------------|-------------|
| O1 | T(p;σ) | Kinetic energy | Momentum |
| O2 | V_LP(x) | Volume-weighted attraction | Liquidity pools |
| O3 | V_OB(x) | Institutional footprint | Order blocks |
| O4 | V_FVG(x) | Imbalance potential | Fair value gaps |
| O5 | V_macro(t) | Session time-decay | Kill zones |
| O6 | V_PD(x) | Price delivery | Premium/discount |
| O7 | V_regime | BOS/CHOCH continuous score | Market regime |
| O8 | Π_session | Trading hours gate | Session filter |
| O9 | Π_risk | Exposure limit gate | Risk management |
| O10 | L(n) | Sailing lane decay | Multi-leg alpha |
| O11 | S_liq | Sweep + reversal speed | Liquidity sweeps |
| O12 | D(x,t) | Displacement score | Impulsive moves |
| O13 | BB(x) | Phase transition proximity | Breaker blocks |
| O14 | MB(x) | Mitigation 1-dist/ATR | Mitigation blocks |
| O15 | OTE(x) | Fibonacci 0.62–0.79 from BOS | Optimal trade entry |
| O16 | J(x,t) | Judas reversal speed | Judas swings |
| O17 | A(x,t) | Wyckoff range compression | Accumulation/distribution |
| O18 | ⟨ψ\|H\|ψ⟩ | Quadratic expectation value | Full quantum readout |

---

## Production Hardening (T3-A)

**Circuit Breaker** — Stage 15 (Scheduler Collapse):
- 10 consecutive failures → circuit opens → `risk_manager.trigger_kill_switch()` fires automatically
- OPEN circuit rejects all collapse attempts immediately
- HALF_OPEN state: 3 successes required to recover

**PnL Divergence Detection** — Stage 17 (Reconciliation):
- Tracks `|predicted_pnl - realized_pnl| / max(|predicted_pnl|, 1.0)` per execution
- >15% divergence → weight penalty applied via `scheduler.update_action_weights()`
- Rolling 100-trade histogram with mean/std/p95 stats

---

## Enhancement Roadmap

See [T3_ROADMAP.md](T3_ROADMAP.md) for the full strategic plan.

| Phase | What | Status |
|-------|------|--------|
| T1 (A/B/C) | Security, 18 operators, regime wiring | COMPLETE |
| T2 (A–H) | Geodesic trajectories, FAISS, PPO, async, dashboard, Mojo | COMPLETE |
| T3-A | Circuit breaker + PnL divergence | COMPLETE |
| T3-C | Prometheus metrics + Grafana | Planned |
| T3-D | Slippage model + partial fill | Planned |
| T3-B | GPU trajectory batching (50–200×) | Planned |
| T3-E | Distributed backtester | Planned |
| T3-F | Ensemble RL + curiosity exploration | Planned |

---

## Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| T2 Integration | 6 | PASSED |
| T3-A Integration | 20 | PASSED |
| Geometry unit tests | 15 | PASSED |
| TAEP unit tests | 8 | PASSED |
| Full pipeline integration | 1 | PASSED |

---

## License

MIT License — See [LICENSE](LICENSE) file.

---

**Version:** 2.0.0 (T3-A)
**Last Updated:** 2026-04-23
