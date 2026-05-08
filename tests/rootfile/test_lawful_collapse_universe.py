"""Lawful-collapse overlay integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from core.economics.qpt_token import mint_qpt_if_applicable
from core.meta import OperatorMeta, declare_operator, get_declared_meta, normalize_meta
from core.orchestration.evidence import EvidenceEvent, emit_evidence
from core.orchestration.reconciliation import ReconciliationReport
from core.rootfile_manifest import LAWS, get_law_dir, validate_manifest_paths
from tachyonic_chain.audit_log import verify_execution_evidence_chain
from tools.validate_rootfile import validate_file, validate_tree
from trading.fields import compute_maxwell_tensor
from trading.fields.minkowski_causality import check_causal_reach
from trading.kernel.H_field import FieldHamiltonian
from trading.pipeline.orchestrator import PipelineContext, PipelineOrchestrator


class _RiskManager:
    max_position_size = 1.0

    def check_all_limits(self, **kwargs):
        class Result:
            passed = True
            message = "ok"

            class Level:
                value = "low"

            level = Level()

        return Result()


def test_rootfile_manifest_resolves_all_laws():
    assert set(LAWS) == {f"H{index}" for index in range(1, 14)}
    assert validate_manifest_paths(Path.cwd()) == []
    for law_id in LAWS:
        assert get_law_dir(law_id).exists()


def test_operator_meta_accepts_dict_and_decorator():
    meta = normalize_meta(
        {
            "tier": "rootfile",
            "layer": "test",
            "operator_type": "unit",
            "canonical_law": "H8",
        }
    )
    assert meta == OperatorMeta("rootfile", "test", "unit", "H8")

    @declare_operator(meta)
    class Projector:
        pass

    assert get_declared_meta(Projector).canonical_law == "H8"


def test_validate_rootfile_accepts_operator_meta_and_rejects_bad_law(tmp_path):
    good = tmp_path / "good.py"
    good.write_text(
        "from core.meta import OperatorMeta\n"
        "META = OperatorMeta(tier='rootfile', layer='x', operator_type='y', canonical_law='H9')\n",
        encoding="utf-8",
    )
    bad = tmp_path / "bad.py"
    bad.write_text(
        "META = {'tier': 'rootfile', 'layer': 'x', 'operator_type': 'y', 'canonical_law': 'H99'}\n",
        encoding="utf-8",
    )

    assert validate_file(good).valid
    bad_report = validate_file(bad)
    assert not bad_report.valid
    assert "unknown canonical_law" in bad_report.issues[0].message


def test_repository_rootfile_validation_passes():
    assert validate_tree(Path.cwd()).valid


def _market_state():
    return {
        "ohlcv": {
            "high": [1.1010, 1.1020],
            "low": [1.0990, 1.1000],
            "close": [1.1000, 1.1015],
        },
        "microstructure": {"mid": 1.1015},
    }


def test_field_tensor_is_deterministic():
    geometry = {"phi": 0.2, "curvature": {"gaussian_curvature": 0.01}}

    first = compute_maxwell_tensor(_market_state(), geometry)
    second = compute_maxwell_tensor(_market_state(), geometry)

    assert first == second
    assert first["field_energy"] > 0


def test_causal_violation_marks_field_inadmissible():
    tensor = {"magnetic_liquidity": 0.00001, "electric_impulse": 0.00001}
    result = check_causal_reach({"entry": 1.0, "target": 2.0}, tensor)

    assert result["causal"] is False
    assert result["reason"] == "causal_violation"


def test_field_hamiltonian_default_stage_records_diagnostics(monkeypatch):
    monkeypatch.delenv("ENABLE_FIELD_HAMILTONIAN", raising=False)
    orchestrator = PipelineOrchestrator(risk_manager=_RiskManager(), use_weight_learning=False)
    context = PipelineContext(symbol="EURUSD", timestamp=1.0, source="test")
    context.market_state = _market_state()
    context.geometry_data = {"phi": 0.0, "curvature": {"gaussian_curvature": 0.0}}

    result = orchestrator._stage_field_evaluation(context)

    assert result["field_evaluated"] is True
    assert result["field_enabled"] is False
    assert "field_tensor" in context.field_data


def test_enabled_field_refusal_blocks_admissibility(monkeypatch):
    monkeypatch.setenv("ENABLE_FIELD_HAMILTONIAN", "1")
    orchestrator = PipelineOrchestrator(risk_manager=_RiskManager(), use_weight_learning=False)
    context = PipelineContext(symbol="EURUSD", timestamp=1.0, source="test")
    context.proposal = {"direction": "buy", "entry": 1.0, "size": 0.1}
    context.field_admissible = False
    context.field_reason = "causal_violation"

    result = orchestrator._stage_admissibility_check(context)

    assert result["admissible"] is False
    assert result["reason"] == "field_hamiltonian_refusal:causal_violation"


def _accepted_report():
    return ReconciliationReport(
        broker="test",
        accepted=True,
        status="match",
        realized_pnl=1.0,
        evidence_valid=True,
        admissible=True,
        information_gain=0.75,
        scheduler_authorized=True,
        execution_id="exec-qpt",
        symbol="EURUSD",
    )


def test_qpt_mints_only_when_enabled_and_all_conditions_pass(tmp_path, monkeypatch):
    ledger = tmp_path / "qpt_ledger.jsonl"
    monkeypatch.setenv("ENABLE_QPT", "1")
    monkeypatch.setenv("APEX_QPT_LEDGER", str(ledger))

    token_id = mint_qpt_if_applicable(_accepted_report())

    assert token_id and token_id.startswith("qpt_")
    record = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert record["token_id"] == token_id
    assert record["conditions"]["reconciliation_accepted"] is True


def test_qpt_does_not_mint_on_refusal(tmp_path, monkeypatch):
    ledger = tmp_path / "qpt_ledger.jsonl"
    monkeypatch.setenv("ENABLE_QPT", "1")
    monkeypatch.setenv("APEX_QPT_LEDGER", str(ledger))
    report = _accepted_report()
    report.accepted = False

    assert mint_qpt_if_applicable(report) is None
    assert not ledger.exists()


def test_evidence_facade_appends_runtime_chain_and_records_anchor_failure(tmp_path, monkeypatch):
    log_path = tmp_path / "execution_evidence.jsonl"
    monkeypatch.setenv("ENABLE_ANCHORING", "1")
    monkeypatch.delenv("APEX_ANCHOR_ENDPOINT", raising=False)

    record_hash = emit_evidence(
        EvidenceEvent(
            event_type="unit_test",
            execution_id="evidence-facade",
            operation="test",
            payload={"value": 1},
        ),
        log_path=str(log_path),
    )

    assert record_hash
    assert verify_execution_evidence_chain(log_path).valid
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())["payload"]
    assert payload["anchor_status"] == "failed"


def test_field_hamiltonian_direct_flat_field_reason():
    result = FieldHamiltonian().evaluate({}, {}, proposal=None)

    assert result.field_admissible is False
    assert "flat_field" in result.reasons
