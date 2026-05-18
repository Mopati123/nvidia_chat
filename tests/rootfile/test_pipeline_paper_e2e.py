from __future__ import annotations

from core.rootfile_manifest import LAWS
from trading.kernel import CollapseDecision, Scheduler
from trading.pipeline.orchestrator import PipelineOrchestrator, PipelineStage
from trading.pipeline.stage_contracts import (
    CANONICAL_STAGE_SEQUENCE,
    STAGE_OPERATOR_SPECS,
    get_stage_operator_spec,
    validate_stage_operator_specs,
)
from trading.risk.risk_manager import ProductionRiskManager


class _OfflineScheduler(Scheduler):
    def __init__(self):
        super().__init__(config={"use_rl": False, "max_entropy": 1.0})
        self.weight_updates = []

    def update_action_weights(self, **kwargs):
        self.weight_updates.append(kwargs)
        return {
            "updated": False,
            "reward": 0.0,
            "new_weights": self.get_action_weights(),
            "reason": "offline_test_noop",
        }


def _synthetic_ohlcv():
    return {
        "open": [1.1000, 1.1002, 1.1004, 1.1006, 1.1008],
        "high": [1.1003, 1.1005, 1.1007, 1.1009, 1.1011],
        "low": [1.0998, 1.1000, 1.1002, 1.1004, 1.1006],
        "close": [1.1002, 1.1004, 1.1006, 1.1008, 1.1010],
        "volume": [100, 120, 140, 160, 180],
        "time": [1, 2, 3, 4, 5],
        "session": "ny",
    }


def _paper_context(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    scheduler = _OfflineScheduler()
    orchestrator = PipelineOrchestrator(
        scheduler=scheduler,
        risk_manager=ProductionRiskManager(max_position_size=1.0),
        use_microstructure=True,
        use_weight_learning=False,
    )
    orchestrator._paper_mode = True
    context = orchestrator.execute(
        _synthetic_ohlcv(),
        symbol="EURUSD",
        source="TEST",
    )
    return context, scheduler


def test_canonical_stage_contracts_cover_sequence_and_laws():
    assert validate_stage_operator_specs() == []
    assert [PipelineStage(stage) for stage in CANONICAL_STAGE_SEQUENCE] == [
        PipelineStage.DATA_INGESTION,
        PipelineStage.STATE_CONSTRUCTION,
        PipelineStage.ICT_EXTRACTION,
        PipelineStage.GEOMETRY_COMPUTATION,
        PipelineStage.FIELD_EVALUATION,
        PipelineStage.TRAJECTORY_GENERATION,
        PipelineStage.RAMANUJAN_COMPRESSION,
        PipelineStage.ADMISSIBILITY_FILTERING,
        PipelineStage.ACTION_EVALUATION,
        PipelineStage.PATH_INTEGRAL,
        PipelineStage.INTERFERENCE_SELECTION,
        PipelineStage.PATH_SELECTION,
        PipelineStage.PROPOSAL_GENERATION,
        PipelineStage.ADMISSIBILITY_CHECK,
        PipelineStage.ENTROPY_GATE,
        PipelineStage.SCHEDULER_COLLAPSE,
        PipelineStage.EXECUTION,
        PipelineStage.RECONCILIATION,
        PipelineStage.EVIDENCE_EMISSION,
        PipelineStage.WEIGHT_UPDATE,
    ]
    for stage in (*CANONICAL_STAGE_SEQUENCE, "completed", "failed"):
        spec = STAGE_OPERATOR_SPECS[stage]
        assert spec.operator_id
        assert spec.canonical_law in LAWS
        assert all(law in LAWS for law in spec.supporting_laws)


def test_execute_runs_complete_paper_mode_order_flow_without_broker_network(
    monkeypatch,
    tmp_path,
):
    context, scheduler = _paper_context(monkeypatch, tmp_path)

    stages = [result.stage for result in context.stage_history]

    assert PipelineStage.FAILED not in stages
    assert stages[:20] == [
        PipelineStage.DATA_INGESTION,
        PipelineStage.STATE_CONSTRUCTION,
        PipelineStage.ICT_EXTRACTION,
        PipelineStage.GEOMETRY_COMPUTATION,
        PipelineStage.FIELD_EVALUATION,
        PipelineStage.TRAJECTORY_GENERATION,
        PipelineStage.RAMANUJAN_COMPRESSION,
        PipelineStage.ADMISSIBILITY_FILTERING,
        PipelineStage.ACTION_EVALUATION,
        PipelineStage.PATH_INTEGRAL,
        PipelineStage.INTERFERENCE_SELECTION,
        PipelineStage.PATH_SELECTION,
        PipelineStage.PROPOSAL_GENERATION,
        PipelineStage.ADMISSIBILITY_CHECK,
        PipelineStage.ENTROPY_GATE,
        PipelineStage.SCHEDULER_COLLAPSE,
        PipelineStage.EXECUTION,
        PipelineStage.RECONCILIATION,
        PipelineStage.EVIDENCE_EMISSION,
        PipelineStage.WEIGHT_UPDATE,
    ]
    assert stages[-1] == PipelineStage.COMPLETED

    assert context.proposal is not None
    assert context.risk_check_passed is True
    assert context.entropy_gate_passed is True
    assert context.collapse_decision == CollapseDecision.AUTHORIZED.name
    assert context.execution_token is not None
    assert scheduler.token_authority.active_count == 0

    assert context.execution_result["status"] == "filled"
    assert context.execution_result["pnl_status"] == "entry_simulated"
    assert context.execution_result["entry_price"] == context.proposal["entry"]
    assert "broker" not in context.execution_result
    assert context.reconciliation_status == "match"
    assert len(context.evidence_hash) == 32


def test_paper_mode_stage_history_is_a_linked_proof_chain(monkeypatch, tmp_path):
    context, _scheduler = _paper_context(monkeypatch, tmp_path)

    previous_hash = ""
    for result in context.stage_history:
        spec = get_stage_operator_spec(result.stage)
        assert result.operator_id == spec.operator_id
        assert result.canonical_law == spec.canonical_law
        assert len(result.input_hash) == 64
        assert len(result.output_hash) == 64
        assert len(result.proof_hash) == 64
        assert result.checkpoint_hash == result.proof_hash[:16]
        assert result.previous_hash == previous_hash
        assert isinstance(result.preconditions, list)
        assert isinstance(result.postconditions, list)
        previous_hash = result.proof_hash

    assert context.stage_history[-1].stage == PipelineStage.COMPLETED
    assert context.stage_history[-1].canonical_law == "H13"


def test_stage_handler_overrides_keep_proof_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    orchestrator = PipelineOrchestrator(
        scheduler=_OfflineScheduler(),
        risk_manager=ProductionRiskManager(max_position_size=1.0),
        use_weight_learning=False,
    )

    def no_op_stage(_context):
        return {"noop": True}

    def collapse_stage(context):
        context.collapse_decision = "REFUSED"
        return {"decision": "REFUSED", "reason": "override_refusal"}

    orchestrator.stage_handlers = {
        stage: no_op_stage
        for stage in orchestrator.stage_handlers
    }
    orchestrator.stage_handlers[PipelineStage.SCHEDULER_COLLAPSE] = collapse_stage

    context = orchestrator.execute(_synthetic_ohlcv(), symbol="EURUSD", source="TEST")
    scheduler_stage = next(
        result
        for result in context.stage_history
        if result.stage == PipelineStage.SCHEDULER_COLLAPSE
    )

    assert scheduler_stage.canonical_law == "H10"
    assert scheduler_stage.refusal_code == "scheduler_collapse:refused:override_refusal"
    assert context.stage_history[-1].stage == PipelineStage.COMPLETED
    assert context.stage_history[-1].previous_hash == scheduler_stage.proof_hash
