"""Focused tests for the implemented Hamiltonian canon gaps."""

from __future__ import annotations

from pathlib import Path

from tachyonic_chain.audit_log import verify_execution_evidence_chain
from trading.feedback.falsification import append_falsification_evidence, score_decision
from trading.kernel.scheduler import CollapseDecision
from trading.pipeline.orchestrator import PipelineContext, PipelineOrchestrator


class _RiskManager:
    kill_switch_active = False

    def trigger_kill_switch(self, reason):
        self.kill_switch_active = True
        self.reason = reason


class _PassthroughBreaker:
    def call(self, fn, **kwargs):
        return True, fn(**kwargs)


def _context_with_weights(weights):
    context = PipelineContext(symbol="EURUSD", timestamp=1.0, source="test")
    context.admissible_paths = [
        {"id": f"traj_{index}", "energy": 0.1, "weight": weight}
        for index, weight in enumerate(weights)
    ]
    return context


def _context_with_actions(actions):
    context = PipelineContext(symbol="EURUSD", timestamp=1.0, source="test")
    context.admissible_paths = [
        {"id": f"traj_{index}", "energy": 0.1, "action": action}
        for index, action in enumerate(actions)
    ]
    return context


def _deriv_style_ohlcv():
    return {
        "open": [1.1000, 1.1001, 1.1007, 1.1010, 1.1009],
        "high": [1.1002, 1.1004, 1.1012, 1.1014, 1.1011],
        "low": [1.0998, 1.1000, 1.1006, 1.1008, 1.1005],
        "close": [1.1001, 1.1003, 1.1010, 1.1009, 1.1006],
        "volume": [200, 300, 250, 220, 280],
        "time": [1.0, 2.0, 3.0, 4.0, 5.0],
        "session": "ny",
    }


def test_measured_delta_s_sharpens_when_path_distribution_concentrates():
    orchestrator = PipelineOrchestrator(
        risk_manager=_RiskManager(),
        use_microstructure=False,
        use_weight_learning=False,
    )

    flat = _context_with_weights([1.0, 1.0, 1.0, 1.0])
    sharp = _context_with_weights([1000.0, 1.0, 1.0, 1.0])

    flat_result = orchestrator._stage_entropy_gate(flat)
    sharp_result = orchestrator._stage_entropy_gate(sharp)

    assert flat_result["prior_entropy"] > 0.999
    assert flat_result["delta_s"] > sharp_result["delta_s"]
    assert sharp_result["information_gain"] > flat_result["information_gain"]
    assert sharp.action_scores["delta_s"] == sharp_result["delta_s"]
    assert sharp.action_scores["information_gain"] == sharp_result["information_gain"]


def test_flat_action_distribution_preserves_entropy_refusal():
    orchestrator = PipelineOrchestrator(
        risk_manager=_RiskManager(),
        use_microstructure=False,
        use_weight_learning=False,
    )
    flat = _context_with_actions([0.25, 0.25, 0.25, 0.25])

    result = orchestrator._stage_entropy_gate(flat)

    assert result["passed"] is False
    assert result["delta_s"] > 0.999
    assert result["posterior_score_source"] == "action"
    assert result["entropy_reason"] == "flat_posterior_distribution"


def test_compressed_action_distribution_is_deterministically_sharpened():
    orchestrator = PipelineOrchestrator(
        risk_manager=_RiskManager(),
        use_microstructure=False,
        use_weight_learning=False,
    )
    sharp = _context_with_actions([0.100001, 0.100020, 0.100030, 0.100050])

    result = orchestrator._stage_entropy_gate(sharp)

    assert result["passed"] is True
    assert result["delta_s"] < 0.5
    assert result["information_gain"] > 0.5
    assert result["posterior_score_source"] == "action"
    assert result["posterior_score_spread"] > 0.0
    assert result["entropy_reason"] == "action_distribution_measured"


def test_stage13_audit_includes_entropy_diagnostics():
    orchestrator = PipelineOrchestrator(
        risk_manager=_RiskManager(),
        use_microstructure=False,
        use_weight_learning=False,
    )
    captured = []
    orchestrator._audit_gate = lambda gate, status, **fields: captured.append((gate, status, fields))
    context = _context_with_actions([0.1, 1.0, 1.1, 1.2])
    context.selected_path = {
        "id": "traj_0",
        "family": "liquidity=fvg1_pool1_sweep1|time=ny|entry=bullish_entry|risk=low|topology=monotonic_bullish",
    }

    result = orchestrator._stage_entropy_gate(context)

    gate, status, fields = captured[-1]
    assert result["passed"] is True
    assert gate == "stage13_entropy"
    assert status == "passed"
    assert fields["path_count"] == 4
    assert fields["posterior_score_source"] == "action"
    assert fields["selected_path_id"] == "traj_0"
    assert fields["selected_family"] == context.selected_path["family"]
    assert float(fields["posterior_score_spread"]) > 0.0


def test_deriv_style_arrays_normalize_to_canonical_bars():
    bars = PipelineOrchestrator._canonical_ohlcv_bars(_deriv_style_ohlcv())

    assert len(bars) == 5
    assert bars[0]["open"] == 1.1000
    assert bars[2]["high"] == 1.1012
    assert bars[4]["timestamp"] == 5.0


def test_ohlcv_only_state_builds_live_microstructure_fields():
    orchestrator = PipelineOrchestrator(
        risk_manager=_RiskManager(),
        use_microstructure=True,
        use_weight_learning=False,
    )
    context = PipelineContext(
        symbol="EURUSD",
        timestamp=1.0,
        source="DERIV",
        raw_data=_deriv_style_ohlcv(),
    )

    result = orchestrator._stage_state_construction(context)
    micro = context.market_state["microstructure"]

    assert result["ohlcv_bars"] == 5
    assert micro["mid"] == 1.1006
    assert micro["spread"] > 0.0
    assert micro["velocity"] != 0.0
    assert "acceleration" in micro


def test_ohlcv_only_ict_context_derives_liquidity_and_fvg_fields():
    orchestrator = PipelineOrchestrator(
        risk_manager=_RiskManager(),
        use_microstructure=True,
        use_weight_learning=False,
    )
    context = PipelineContext(
        symbol="EURUSD",
        timestamp=1.0,
        source="DERIV",
        raw_data=_deriv_style_ohlcv(),
    )
    orchestrator._stage_state_construction(context)

    result = orchestrator._stage_ict_extraction(context)

    assert result["ict_extracted"] is True
    assert context.ict_geometry["current_session"] == "ny"
    assert len(context.ict_geometry["liquidity_zones"]) == 2
    assert context.ict_geometry["liquidity_zones"][0]["source"] == "ohlcv_recent_high"
    assert context.ict_geometry["fvgs"]


def test_stage7_creates_nonflat_action_costs_from_ohlcv_only_inputs():
    orchestrator = PipelineOrchestrator(
        risk_manager=_RiskManager(),
        use_microstructure=True,
        use_weight_learning=False,
    )
    context = PipelineContext(
        symbol="EURUSD",
        timestamp=1.0,
        source="DERIV",
        raw_data=_deriv_style_ohlcv(),
    )
    orchestrator._stage_state_construction(context)
    orchestrator._stage_ict_extraction(context)
    context.admissible_paths = [
        {"id": "up", "path": [(0.0, 1.1006), (1.0, 1.1010), (2.0, 1.1014)]},
        {"id": "down", "path": [(0.0, 1.1006), (1.0, 1.1001), (2.0, 1.0998)]},
        {"id": "turn", "path": [(0.0, 1.1006), (1.0, 1.1010), (2.0, 1.1002)]},
    ]

    result = orchestrator._stage_action_evaluation(context)
    actions = [
        context.action_scores[path["id"]]["total_action"]
        for path in context.admissible_paths
    ]
    entropy = orchestrator._stage_entropy_gate(context)

    assert result["actions_computed"] == 3
    assert result["action_spread"] > 0.0
    assert any(action > 0.0 for action in actions)
    assert len({round(action, 12) for action in actions}) > 1
    assert all(
        context.action_scores[path["id"]]["path_feature_source"] == "ohlcv_fallback"
        for path in context.admissible_paths
    )
    assert entropy["posterior_score_source"] == "action"
    assert entropy["posterior_score_spread"] > 0.0
    assert entropy["entropy_reason"] == "action_distribution_measured"


def test_scheduler_receives_measured_delta_s_from_context():
    class RecorderScheduler:
        config = {"max_entropy": 0.5}

        def __init__(self):
            self.seen_delta_s = None

        def authorize_collapse(self, **kwargs):
            self.seen_delta_s = kwargs["delta_s"]
            return CollapseDecision.REFUSED, None

    scheduler = RecorderScheduler()
    orchestrator = PipelineOrchestrator(
        scheduler=scheduler,
        risk_manager=_RiskManager(),
        use_microstructure=False,
        use_weight_learning=False,
    )
    orchestrator.collapse_breaker = _PassthroughBreaker()

    context = PipelineContext(symbol="EURUSD", timestamp=1.0, source="test")
    context.risk_check_passed = True
    context.proposal = {"symbol": "EURUSD", "size": 0.01}
    context.admissible_paths = [{"id": "traj_a", "energy": 0.1, "action": 0.2}]
    context.entropy_gate_passed = True
    context.action_scores["delta_s"] = 0.217
    context.action_scores["information_gain"] = 0.783

    result = orchestrator._stage_scheduler_collapse(context)

    assert result["decision"] == CollapseDecision.REFUSED.name
    assert scheduler.seen_delta_s == 0.217


def test_scheduler_not_called_when_entropy_gate_failed():
    class GuardedScheduler:
        config = {"max_entropy": 0.5}

        def authorize_collapse(self, **kwargs):
            raise AssertionError("scheduler must not run after entropy refusal")

    orchestrator = PipelineOrchestrator(
        scheduler=GuardedScheduler(),
        risk_manager=_RiskManager(),
        use_microstructure=False,
        use_weight_learning=False,
    )
    orchestrator.collapse_breaker = _PassthroughBreaker()

    context = _context_with_actions([0.25, 0.25, 0.25, 0.25])
    context.risk_check_passed = True
    context.proposal = {"symbol": "EURUSD", "size": 0.01}
    entropy = orchestrator._stage_entropy_gate(context)

    result = orchestrator._stage_scheduler_collapse(context)

    assert entropy["passed"] is False
    assert result["authorized"] is False
    assert result["reason"].startswith("entropy_gate_not_passed")


def test_ramanujan_signatures_are_deterministic_behavior_families():
    orchestrator = PipelineOrchestrator(
        risk_manager=_RiskManager(),
        use_microstructure=False,
        use_weight_learning=False,
    )
    context = PipelineContext(symbol="EURUSD", timestamp=1.0, source="test")
    context.ict_geometry = {
        "fvg_zones": [{"low": 1.10, "high": 1.11}],
        "liquidity_pools": [{"price": 1.12}],
        "sweeps": [{"side": "buy"}],
        "session": "NY AM",
    }
    context.trajectories = [
        {"id": "up", "path": [(0, 1.1000), (1, 1.1004), (2, 1.1008)]},
        {"id": "down", "path": [(0, 1.1000), (1, 1.0996), (2, 1.0992)]},
        {"id": "turn", "path": [(0, 1.1000), (1, 1.1004), (2, 1.0998)]},
    ]

    first = orchestrator._stage_ramanujan_compression(context)
    second = orchestrator._stage_ramanujan_compression(context)

    assert first == second
    assert context.path_signatures["up"]["topology"] == "monotonic_bullish"
    assert context.path_signatures["down"]["entry"] == "bearish_entry"
    assert context.path_signatures["turn"]["topology"] == "oscillating"
    assert all("liquidity=fvg1_pool1_sweep1" in key for key in context.path_families)


def test_falsification_classifies_refusals_and_authorizations():
    avoided = score_decision("REFUSED", would_have_pnl=-1.0, symbol="EURUSD")
    missed = score_decision("REFUSED", would_have_pnl=1.5, symbol="EURUSD")
    authorized = score_decision("AUTHORIZED", realized_pnl=0.25, symbol="EURUSD")

    assert avoided.classification == "avoided_loss"
    assert avoided.correct is True
    assert missed.classification == "missed_opportunity"
    assert missed.correct is False
    assert authorized.classification == "correct_authorization"
    assert authorized.correct is True


def test_falsification_evidence_preserves_hash_chain(tmp_path: Path):
    evidence_path = tmp_path / "execution_evidence.jsonl"

    first = score_decision(
        "REFUSED",
        would_have_pnl=-0.5,
        symbol="EURUSD",
        broker="mt5",
        reference_id="refusal_a",
    )
    second = score_decision(
        "AUTHORIZED",
        realized_pnl=-1.0,
        symbol="EURUSD",
        broker="deriv",
        reference_id="contract_a",
    )

    append_falsification_evidence(first, evidence_path)
    append_falsification_evidence(second, evidence_path)

    assert first.evidence_hash is not None
    assert second.evidence_hash is not None
    assert verify_execution_evidence_chain(evidence_path).valid
