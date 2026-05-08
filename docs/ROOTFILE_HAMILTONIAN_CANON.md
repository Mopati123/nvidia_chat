# Rootfile Hamiltonian Canon

## Summary

The rootfile trading runtime is best described as lawful collapse of possible
market futures into auditable state.

The original canon uses the phrase "nine Hamiltonians", but the working system
maps more accurately to thirteen operational laws. Those thirteen laws are the
canonical architecture layer for this repository. They sit above the active
pipeline stages, broker settlement modules, evidence chain, and ML feedback
path.

The practical runtime flow is:

```text
raw state -> geometry -> paths -> action -> projectors -> entropy
-> scheduler -> execution -> reconciliation -> evidence -> ML feedback
```

The lawful-collapse overlay makes that flow self-describing:

```text
raw state -> geometry -> field tensor -> paths -> action -> projectors
-> entropy -> lambda scheduler -> execution -> reconciliation
-> evidence -> optional QPT minting -> ML feedback
```

## One-To-One Rootfile Map

| Canon law | Existing rootfile home | Current implementation meaning |
|---|---|---|
| H1 State space | `PipelineContext`, data ingestion, state construction | MT5, Deriv, and replay inputs become market state, OHLCV, microstructure, symbol, source, and stage context. |
| H2 Geometry | `trading/geometry/liquidity_field.py`, `metric.py` | ICT and microstructure features become liquidity field `phi` and the conformal metric. |
| H3 Connection | `trading/geometry/connection.py` | Christoffel symbols bend candidate trajectories through liquidity gradients. |
| H4 Curvature | `trading/geometry/curvature.py` | Gaussian curvature classifies basin, flat, saddle, and transition regimes. |
| H5 Path space | `trading/path_integral/trajectory_generator.py` | Candidate futures are generated as trajectories through market state space. |
| H6 Ramanujan compression | Pipeline Ramanujan compression stage | Trajectories are grouped into deterministic behavior families using liquidity, time, entry, risk, and topology signatures. |
| H7 Action | Pipeline action evaluation and `trading/action/*` | Paths receive weighted liquidity, time, entry, risk, and curvature-aware costs. |
| H8 Admissibility | Pipeline admissibility stages and `trading/risk/risk_manager.py` | Illegal paths and unsafe proposals are refused before execution. |
| H9 Entropy / delta S | Pipeline entropy gate and scheduler `delta_s` input | The gate measures prior path uncertainty, posterior action-weight uncertainty, and information gain before scheduler collapse. |
| H10 Scheduler authority | `trading/kernel/scheduler.py` and scheduler-collapse stage | The scheduler is the sole authority that may issue an execution token. |
| H11 Collapse / execution | Pipeline execution stage, broker modules, demo runner | Authorized proposals become paper fills, MT5 demo orders, or Deriv demo contracts. |
| H12 Reconciliation | Pipeline reconciliation plus MT5 and Deriv settlement modules | Intended vs actual execution is checked; realized closed-trade PnL feeds settlement and learning. |
| H13 Evidence | `tachyonic_chain/audit_log.py`, `trading/evidence/evidence_chain.py`, audit CLIs | Runtime evidence is a SHA-256 JSONL hash chain; the separate evidence bundle path supports Merkle roots and Ed25519 signatures where used. |

`core/rootfile_manifest.py` is the source of truth for law ownership,
invariants, and allowed couplings. `tools/validate_rootfile.py` checks declared
operator metadata against that manifest in CI.

## Active Pipeline Alignment

The active `PipelineOrchestrator` runs nineteen decision stage handlers plus
completion or failure bookkeeping. Older summaries call this a 20-stage pipeline
because `COMPLETED` is counted as a terminal stage result.

| Runtime stage group | Canon coverage |
|---|---|
| Data ingestion and state construction | H1 |
| ICT extraction, liquidity field, metric, connection, curvature | H2, H3, H4 |
| Field tensor diagnostics | H8-adjacent admissibility overlay |
| Trajectory generation and path-family compression | H5, H6 |
| Action evaluation, path integral, interference, path selection | H7 |
| Proposal generation and admissibility checks | H8 |
| Entropy gate | H9 |
| Scheduler collapse | H10 |
| Execution | H11 |
| Reconciliation | H12 |
| Evidence emission and weight update | H13 plus ML feedback |

Broker settlement is deliberately outside the immediate tick-loop collapse
because MT5 positions and Deriv contracts close asynchronously. Settlement is
the bridge from broker reality back into learning:

| Broker path | Settlement path | Learning rule |
|---|---|---|
| MT5 demo order | `scripts.trading.settle_demo_trades` | Use realized position history, not floating open PnL. |
| Deriv demo contract | `scripts.trading.settle_deriv_contracts` | Use closed contract profit/loss, not proposal-time payout estimates. |

## Evidence And Anchoring

There are two evidence layers, and they should not be conflated:

| Layer | Implementation | What it proves |
|---|---|---|
| Runtime execution evidence | `tachyonic_chain/audit_log.py` | Each JSONL record stores `previous_hash`, canonical payload data, and `record_hash` using SHA-256. |
| Optional evidence bundles | `trading/evidence/evidence_chain.py` | Bundle-level Merkle roots and Ed25519 signatures where that path is used. |

GitHub commits then publicly anchor the code and curated reports. That is not a
public blockchain transaction; it is public source-control anchoring layered on
top of the local evidence hash chain.

`core/orchestration/evidence.py` is the unified evidence facade. It writes to the
runtime SHA-256 chain and records optional anchoring status. External anchoring is
disabled by default; when enabled without a configured endpoint, the pipeline
records `anchor_status=failed` and continues without blocking collapse handling.

## Field Hamiltonian

`trading/fields` and `trading/kernel/H_field.py` add a diagnostics-first field
layer between geometry and path generation:

- Maxwell tensor: electric impulse and magnetic liquidity diagnostics.
- Minkowski causality: whether proposed displacement is reachable under the
  current field.
- Polarity detection: directional phase inference.
- Magnetoelectric coupling: field strength summary.

By default, the field stage records diagnostics only. Setting
`ENABLE_FIELD_HAMILTONIAN=1` turns field inadmissibility into a hard refusal input
before scheduler collapse. This preserves safety while allowing calibration.

## QPT Minting

`core/economics/qpt_token.py` is disabled unless `ENABLE_QPT=1`. When enabled, it
mints a local `qpt_*.jsonl` record only if reconciliation is accepted,
admissibility passed, information gain meets threshold, scheduler authority was
present, and evidence is valid. A QPT token is therefore an artifact of proven
collapse, not a substitute for proof.

## What We Have Now

The merged rootfile system has proven:

- MT5 demo execution, settlement, evidence, and offline ML rebuild from a closed
  take-profit trade.
- Deriv demo execution, settlement, evidence, and offline ML rebuild from a
  closed one-contract canary.
- Scheduler-token enforcement before broker execution.
- Durable Deriv PPO pending-state persistence before the canary runner stops.
- V1 Ramanujan path-family signatures in the active pipeline.
- Measured entropy and information-gain reporting into scheduler collapse.
- Post-outcome falsification scoring for closed MT5 and Deriv demo settlements.

The next proof target is a second guarded Deriv demo contract where settlement
returns PPO feedback as `updated` or `transition_stored` instead of
`missing_pending_state`.

## Known Weak Spots

- Ramanujan compression now has deterministic v1 signatures. Future work can
  deepen the signatures with richer ICT lineage and empirical family scoring.
- The entropy gate now measures prior/posterior uncertainty. Future work should
  calibrate the threshold empirically against the 300-shadow/forward proof set.
- Runtime evidence is SHA-256 hash chained; public-chain notarization would be a
  separate explicit feature.
