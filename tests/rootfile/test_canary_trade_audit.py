"""Read-only canary trade audit tests."""

from pathlib import Path

from scripts.trading.audit_canary_trade import audit_canary_trade
from tachyonic_chain.audit_log import append_execution_evidence


def _write_csv(path: Path, ticket: str = "352937676") -> None:
    path.write_text(
        "\n".join([
            "time,symbol,direction,entry,stop,target,size,ticket,predicted_pnl,source",
            f"2026-05-04T09:27:26.368019,EURUSD,buy,1.17241,1.17141,1.17441,0.01,{ticket},0.2,mt5",
            "",
        ]),
        encoding="utf-8",
    )


def _write_success_evidence(path: Path, ticket: str = "352937676") -> None:
    append_execution_evidence(
        event_type="broker_execution",
        execution_id=f"mt5_{ticket}",
        operation="live_execution",
        symbol="EURUSD_r",
        outcome="success",
        token_status="authorized",
        payload={
            "ask": 1.17242,
            "bid": 1.17241,
            "broker": "mt5",
            "comment": "ApexQuantumICT",
            "price": 1.17242,
            "retcode": 10009,
            "symbol": "EURUSD_r",
            "ticket": int(ticket),
            "volume": 0.01,
        },
        log_path=path,
    )


def test_canary_audit_classifies_execution_passed_learning_flagged(tmp_path: Path):
    log_path = tmp_path / "live.err.log"
    csv_path = tmp_path / "demo.csv"
    evidence_path = tmp_path / "evidence.jsonl"

    log_path.write_text(
        "\n".join([
            "MT5 demo connected",
            "Pipeline paper_mode=False (LIVE DEMO - real orders)",
            "Stage 16: MT5 order placed ticket=352937676 BUY EURUSD size=0.01",
            "Stage 17: PnL divergence 20.0% > 15% (predicted=0.20, realized=0.00)",
            "Weight update blocked: Pi_total constraints not passed",
        ]),
        encoding="utf-8",
    )
    _write_csv(csv_path)
    _write_success_evidence(evidence_path)

    report = audit_canary_trade("352937676", log_path, csv_path, evidence_path)

    assert report.execution_path_passed is True
    assert report.learning_flagged is True
    assert report.classification == "EXECUTION_PATH_PASSED_LEARNING_FLAGGED"
    gate_status = {gate.name: gate.status for gate in report.gates}
    assert gate_status["stage12_admissibility"] == "inferred"
    assert gate_status["stage15_scheduler"] == "inferred"
    assert gate_status["mt5_broker_execution"] == "passed"
    assert gate_status["artifact_consistency"] == "passed"


def test_canary_audit_uses_explicit_stage_markers(tmp_path: Path):
    log_path = tmp_path / "live.err.log"
    csv_path = tmp_path / "demo.csv"
    evidence_path = tmp_path / "evidence.jsonl"

    log_path.write_text(
        "\n".join([
            "MT5 demo connected",
            "Pipeline paper_mode=False (LIVE DEMO - real orders)",
            "CANARY_AUDIT gate=stage12_admissibility status=passed symbol=EURUSD",
            "CANARY_AUDIT gate=stage15_scheduler status=passed decision=AUTHORIZED",
            "CANARY_AUDIT gate=stage16_execution status=passed broker=mt5 ticket=352937676",
            "CANARY_AUDIT gate=stage17_reconciliation status=passed status=match",
            "CANARY_AUDIT gate=stage19_weight_update status=passed",
        ]),
        encoding="utf-8",
    )
    _write_csv(csv_path)
    _write_success_evidence(evidence_path)

    report = audit_canary_trade("352937676", log_path, csv_path, evidence_path)

    assert report.classification == "EXECUTION_PATH_PASSED"
    assert not report.learning_flagged
    gate_status = {gate.name: gate.status for gate in report.gates}
    assert gate_status["stage12_admissibility"] == "passed"
    assert gate_status["stage15_scheduler"] == "passed"


def test_canary_audit_blocks_failed_mt5_retcode(tmp_path: Path):
    log_path = tmp_path / "live.err.log"
    csv_path = tmp_path / "demo.csv"
    evidence_path = tmp_path / "evidence.jsonl"

    log_path.write_text(
        "\n".join([
            "MT5 demo connected",
            "Pipeline paper_mode=False (LIVE DEMO - real orders)",
            "Stage 16: no broker available for live execution - order not placed",
        ]),
        encoding="utf-8",
    )
    _write_csv(csv_path)
    append_execution_evidence(
        event_type="broker_execution",
        execution_id="mt5_failed_EURUSD_r",
        operation="live_execution",
        symbol="EURUSD_r",
        outcome="failed",
        token_status="authorized",
        payload={"broker": "mt5", "ticket": 352937676, "retcode": 10027, "volume": 0.01},
        log_path=evidence_path,
    )

    report = audit_canary_trade("352937676", log_path, csv_path, evidence_path)

    assert report.classification == "BLOCKED"
    assert not report.execution_path_passed
    assert any("retcode" in blocker for blocker in report.blockers)
