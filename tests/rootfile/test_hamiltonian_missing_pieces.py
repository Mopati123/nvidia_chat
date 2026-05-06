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
    context.action_scores["delta_s"] = 0.217
    context.action_scores["information_gain"] = 0.783

    result = orchestrator._stage_scheduler_collapse(context)

    assert result["decision"] == CollapseDecision.REFUSED.name
    assert scheduler.seen_delta_s == 0.217


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
