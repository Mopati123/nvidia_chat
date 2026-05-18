# Rootfile Superposition And Evolution Architecture Trace

## Snapshot

- Source graph: `.understand-anything/knowledge-graph.json`
- Rootfile summary: `.understand-anything/rootfile-analysis.md`
- Graph analyzed at: 2026-05-13T11:33:15.390Z
- Git commit recorded by graph: c08fa30c99674c42e3b597bf0a0579eee6c60d68
- Graph size: 326 analyzed files, 1221 nodes, 1243 edges, 17 layers, 8 tour steps

This view treats the repository as one coherent trading organism. The system holds possible market futures in superposition until admissibility, entropy, and scheduler authority collapse one lawful path into execution or refusal. Evidence then records the observed outcome and settlement feeds learning.

## Coherent Architecture

| Layer | Nodes | Role in the system |
|---|---:|---|
| .github | 3 | Repository automation and rootfile CI gates. |
| Application Interfaces | 9 | User-facing and integration surfaces that may observe or command the runtime. |
| Backend API | 3 | API entrypoints and service support without bypassing authority. |
| Configuration | 1 | Runtime configuration used by the architecture. |
| Core Canonical Runtime | 35 | Rootfile overlay for authority, orchestration, execution, simulation, economics, and self-healing. |
| Data Core | 6 | Data normalization and ML/data preparation. |
| Documentation | 25 | The architectural narrative and operating records. |
| Evidence Chain | 3 | Hash-chained runtime evidence and proof primitives. |
| Infrastructure | 1 | Deployment descriptors. |
| Operational Scripts | 26 | Broker setup, demo trading, validation, settlement, and audit commands. |
| Registry Metadata | 4 | Operator catalogs and metadata. |
| Repository Root | 12 | Root manifests, app descriptors, and entry documents. |
| TAEP Authority | 19 | Hamiltonian, quantum, and TAEP authority components. |
| Tests | 31 | Unit, integration, performance, and rootfile proof suites. |
| Tools | 6 | Static validation and architecture guard tools. |
| Trading Engine | 117 | Pipeline, geometry, path/action logic, brokers, feedback, and scheduler runtime. |
| Validation | 27 | Preflight and root-level validation utilities. |

The strongest graph connections show the architecture is not a pile of independent folders. It is a test-observed, validator-constrained, authority-gated runtime:

| Connection | Edge count | Meaning |
|---|---:|---|
| Tests -> Trading Engine | 42 | The trading runtime is heavily observed by tests. |
| Validation -> Trading Engine | 22 | Validation tools check trading behavior and safety boundaries. |
| Core Canonical Runtime -> Trading Engine | 15 | The rootfile overlay governs live trading modules. |
| Tests -> Core Canonical Runtime | 11 | Rootfile authority and orchestration contracts are tested directly. |
| Trading Engine -> TAEP Authority | 9 | Trading decisions depend on Hamiltonian and authority concepts. |
| Tests -> Evidence Chain | 7 | Evidence-chain integrity is a first-class proof target. |
| Operational Scripts -> Trading Engine | 7 | Runners and settlement tools drive the engine operationally. |
| Trading Engine -> Evidence Chain | 6 | Execution, refusal, audit, and settlement events become evidence. |
| Application Interfaces -> Trading Engine | 5 | Interfaces route into the trading system without owning collapse authority. |
| Core Canonical Runtime -> Evidence Chain | 3 | Canonical evidence facades write to the audit chain. |

## Superposition Model

Before execution, the system intentionally keeps many possible futures alive:

1. Raw broker, replay, or synthetic bars become typed market state.
2. ICT and microstructure features become liquidity fields, metric geometry, connection, curvature, and field diagnostics.
3. The trajectory generator creates candidate future paths.
4. Ramanujan compression groups paths into deterministic behavior families.
5. Action scoring, path integral weighting, and interference selection rank the candidate futures.
6. Proposal generation extracts one trade candidate, but it is still only a proposal.
7. Admissibility and entropy decide whether the proposal may even reach scheduler authority.

This is the repository's superposition zone. The observable state includes:

- `PipelineContext.market_state`
- `PipelineContext.trajectories`
- `PipelineContext.admissible_paths`
- `PipelineContext.action_scores`
- `PipelineContext.selected_path`
- `PipelineContext.proposal`
- `PipelineContext.risk_check_passed`
- `PipelineContext.entropy_gate_passed`
- `PipelineContext.entropy_gate_message`
- `PipelineContext.stage_history`

Nothing in this zone should be able to place a broker order. The system can compute, score, refuse, and explain, but not execute.

## Collapse And Evolution

Collapse begins only when scheduler authority is reached. `PipelineContext.stage_history` is the canonical trace spine.

| Stage | Rootfile law | Observation |
|---|---|---|
| `DATA_INGESTION` | H1 State Space | Raw input enters the run. |
| `STATE_CONSTRUCTION` | H1 State Space | Typed market state is formed. |
| `ICT_EXTRACTION` | H2 Geometry | Liquidity and ICT structure are extracted. |
| `GEOMETRY_COMPUTATION` | H2-H4 Geometry, Connection, Curvature | Market structure becomes metric and curvature context. |
| `FIELD_EVALUATION` | H8 Admissibility overlay | Field diagnostics may add refusal pressure. |
| `TRAJECTORY_GENERATION` | H5 Path Space | Candidate futures enter superposition. |
| `RAMANUJAN_COMPRESSION` | H6 Ramanujan Compression | Candidate futures are grouped into behavior families. |
| `ADMISSIBILITY_FILTERING` | H8 Admissibility | Obviously invalid paths are filtered before action scoring. |
| `ACTION_EVALUATION` | H7 Action | Paths receive deterministic action costs. |
| `PATH_INTEGRAL` | H7 Action | Path weights are computed. |
| `INTERFERENCE_SELECTION` | H7 Action | Competing futures interfere and sharpen selection. |
| `PATH_SELECTION` | H7 Action | A least-action candidate is selected. |
| `PROPOSAL_GENERATION` | H8 Admissibility | The selected path becomes a proposed trade. |
| `ADMISSIBILITY_CHECK` | H8 Admissibility | Risk checks decide whether the proposal is lawful enough to continue. |
| `ENTROPY_GATE` | H9 Entropy | Information gain is measured before scheduler authority. |
| `SCHEDULER_COLLAPSE` | H10 Scheduler Authority | The scheduler either refuses or issues an execution token. |
| `EXECUTION` | H11 Collapse Execution | Paper, MT5, or Deriv execution happens only with authority. |
| `RECONCILIATION` | H12 Reconciliation | Intended and realized broker state are compared. |
| `EVIDENCE_EMISSION` | H13 Evidence | The run emits a verifiable evidence hash and optional economic proof. |
| `WEIGHT_UPDATE` | H12-H13 Feedback | Learning receives settlement/reconciliation signal when enabled. |
| `COMPLETED` | H13 Evidence | The observed run is terminal and auditable. |

The collapse path is:

```text
superposed paths
-> selected path
-> proposal
-> admissibility pass/refusal
-> entropy pass/refusal
-> scheduler authorized/refused
-> execution/no execution
-> reconciliation
-> evidence
-> learning feedback
```

## Rootfile Law Chain

| Law | Meaning | Primary runtime area | Observable evolution |
|---|---|---|---|
| H1 State Space | Raw market data becomes typed runtime state. | `trading/pipeline` | Input bars/ticks become `market_state`. |
| H2 Geometry | Liquidity structure becomes metric geometry. | `trading/geometry` | ICT and microstructure become metric context. |
| H3 Connection | Liquidity gradients bend trajectory evolution. | `trading/geometry` | Candidate paths respond to connection terms. |
| H4 Curvature | Curvature classifies market regime stress. | `trading/geometry` | Regime pressure shapes path preference. |
| H5 Path Space | Possible futures are generated as candidate paths. | `trading/path_integral` | `trajectories` holds market futures in superposition. |
| H6 Ramanujan Compression | Candidate paths compress into deterministic families. | `trading/pipeline` | `family` and `signature` group path behavior. |
| H7 Action | Paths receive weighted cost and action scores. | `trading/action` and pipeline scoring | Lower-action paths become stronger candidates. |
| H8 Admissibility | Forbidden proposals are refused before collapse. | `trading/risk` and pipeline gates | Unsafe proposals terminate before scheduler authority. |
| H9 Entropy | Information gain is measured before scheduler authority. | pipeline entropy gate | Flat uncertainty refuses collapse; sharper information can continue. |
| H10 Scheduler Authority | Only scheduler authority may issue execution tokens. | `trading/kernel` and `core/orchestration` | Scheduler returns `AUTHORIZED` or `REFUSED`. |
| H11 Collapse Execution | Authorized proposals become controlled side effects. | `core/execution` and brokers | Broker boundaries validate tokens before side effects. |
| H12 Reconciliation | Broker reality reconciles intended and realized state. | `trading/feedback` | Fill/settlement reality drives feedback. |
| H13 Evidence | Every collapse or refusal leaves verifiable evidence. | `tachyonic_chain` | JSONL evidence links records by hash. |

## Feedback Loops

The coherent system evolves through four loops:

1. Runtime loop: `scripts/trading/run_demo_trading.py` feeds market data into `PipelineOrchestrator.execute(...)`, then records execution, settlement, and learning artifacts.
2. Authority loop: `core/authority`, `trading/kernel/scheduler.py`, and broker adapters ensure no execution boundary acts without scheduler-issued permission.
3. Evidence loop: `core/orchestration/evidence.py` and `tachyonic_chain/audit_log.py` turn refusals, broker outcomes, settlements, and learning feedback into a hash chain.
4. Verification loop: `tests/rootfile`, `tools`, `validation`, and `.github/workflows/rootfile-runtime.yml` keep the architecture observable and enforceable.

## Offline Observation Path

The first safe observation is the paper-mode end-to-end trace in `tests/rootfile/test_pipeline_paper_e2e.py`.

That test observes the whole run without broker network calls:

- all 20 decision stages appear in order,
- no `FAILED` stage appears,
- the proposal exists,
- risk and entropy pass,
- scheduler collapse authorizes,
- the execution token is released,
- paper execution fills without a broker,
- reconciliation reports `match`,
- evidence hash is present.

That gives us a controlled way to observe the system in superposition, watch it collapse, and confirm the evidence trail before any Deriv or MT5 live-demo run.

## Architectural Reading

The architecture is strongest where it refuses to let one layer do too much:

- `trading/` generates and scores possibilities.
- `core/` defines canonical authority and execution boundaries.
- `trading/kernel/` owns scheduler collapse.
- broker adapters perform side effects only after token validation.
- `tachyonic_chain/` proves what happened.
- `tests/rootfile/` and `validation/` observe whether the law was kept.

The main design risk remains concentration: `PipelineOrchestrator` is the central evolution engine and therefore carries a lot of responsibility. The offsetting strength is that the system records `stage_history`, validates tokens at broker boundaries, and has rootfile tests that watch the critical transitions from superposition to collapse to evidence.
