"""Evidence dataset and offline ML pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

from data_core.ml.evidence_dataset import (
    DATASET_COLUMNS,
    audit_record_to_refusal_example,
    build_refusal_risk_dataset,
    read_refusal_risk_dataset,
    sanitize_audit_record,
)
from data_core.ml.refusal_risk_trainer import train_refusal_risk_model
from tachyonic_chain.audit_log import (
    append_execution_evidence,
    iter_execution_evidence,
    verify_execution_evidence_chain,
)


def _append_sample_log(path: Path) -> None:
    append_execution_evidence(
        event_type="broker_refusal",
        execution_id="exec_refused",
        operation="live_execution",
        symbol="EURUSD",
        outcome="refused",
        token_status="missing execution token",
        payload={"broker": "mt5", "direction": "buy", "volume": 0.01},
        log_path=path,
    )
    append_execution_evidence(
        event_type="shadow_execution",
        execution_id="exec_success",
        operation="shadow_execution",
        symbol="BTCUSD",
        outcome="success",
        token_status="authorized",
        evidence_hash="abc123",
        payload={
            "mode": "shadow",
            "bias": "bullish",
            "pnl_prediction": 1.25,
            "execution_time_ms": 0.42,
            "api_key": "SHOULD_NOT_EXPORT",
            "account_id": "123456",
        },
        log_path=path,
    )
    append_execution_evidence(
        event_type="broker_execution",
        execution_id="exec_failed",
        operation="live_execution",
        symbol="R_100",
        outcome="failed",
        token_status="authorized",
        payload={"broker": "deriv", "contract_type": "CALL", "amount": 1.0, "retcode": 10027},
        log_path=path,
    )


def test_verify_execution_evidence_chain_accepts_valid_log(tmp_path: Path):
    log_path = tmp_path / "evidence.jsonl"
    _append_sample_log(log_path)

    report = verify_execution_evidence_chain(log_path)

    assert report.valid
    assert list(iter_execution_evidence(log_path))


def test_verify_execution_evidence_chain_rejects_tampered_record(tmp_path: Path):
    log_path = tmp_path / "evidence.jsonl"
    _append_sample_log(log_path)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    middle = json.loads(lines[1])
    middle["outcome"] = "failed"
    lines[1] = json.dumps(middle, sort_keys=True, separators=(",", ":"))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify_execution_evidence_chain(log_path)

    assert not report.valid
    assert any("record_hash mismatch" in issue.message for issue in report.issues)


def test_verify_execution_evidence_chain_rejects_broken_previous_hash(tmp_path: Path):
    log_path = tmp_path / "evidence.jsonl"
    _append_sample_log(log_path)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["previous_hash"] = "broken"
    lines[1] = json.dumps(second, sort_keys=True, separators=(",", ":"))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify_execution_evidence_chain(log_path)

    assert not report.valid
    assert any("previous_hash mismatch" in issue.message for issue in report.issues)


def test_empty_log_exports_zero_examples(tmp_path: Path):
    log_path = tmp_path / "empty.jsonl"
    output_path = tmp_path / "refusal_risk.parquet"
    log_path.write_text("", encoding="utf-8")

    report = build_refusal_risk_dataset(log_path, output_path)

    assert report.valid
    assert report.rows == 0
    assert output_path.exists()
    assert read_refusal_risk_dataset(output_path) == []


def test_dataset_labels_refusal_success_and_failed_records():
    refused = audit_record_to_refusal_example({
        "operation": "live_execution",
        "outcome": "refused",
        "token_status": "missing execution token",
        "payload": {"volume": 0.01},
    })
    success = audit_record_to_refusal_example({
        "operation": "shadow_execution",
        "outcome": "success",
        "token_status": "authorized",
        "payload": {"pnl_prediction": 0.5},
    })
    failed = audit_record_to_refusal_example({
        "operation": "live_execution",
        "outcome": "failed",
        "token_status": "authorized",
        "payload": {"retcode": 10027},
    })

    assert refused["risk_label"] == 1
    assert success["risk_label"] == 0
    assert failed["risk_label"] == 1


def test_sanitize_audit_record_drops_secret_like_payload_fields():
    sanitized = sanitize_audit_record({
        "timestamp": 1.0,
        "event_type": "shadow_execution",
        "operation": "shadow_execution",
        "symbol": "EURUSD",
        "outcome": "success",
        "token_status": "authorized",
        "payload": {
            "api_key": "SHOULD_NOT_EXPORT",
            "password": "SHOULD_NOT_EXPORT",
            "broker_token": "SHOULD_NOT_EXPORT",
            "account_id": "SHOULD_NOT_EXPORT",
            "volume": 0.01,
        },
    })

    assert set(sanitized) == set(DATASET_COLUMNS)
    assert "SHOULD_NOT_EXPORT" not in json.dumps(sanitized)
    assert sanitized["volume"] == 0.01


def test_build_refusal_risk_dataset_writes_readable_parquet(tmp_path: Path):
    log_path = tmp_path / "evidence.jsonl"
    output_path = tmp_path / "refusal_risk.parquet"
    _append_sample_log(log_path)

    report = build_refusal_risk_dataset(log_path, output_path)
    rows = read_refusal_risk_dataset(output_path)

    assert report.valid
    assert report.rows == 3
    assert len(rows) == 3
    assert set(rows[0]) == set(DATASET_COLUMNS)
    assert {row["risk_label"] for row in rows} == {0, 1}


def test_train_refusal_risk_model_is_deterministic_and_offline(tmp_path: Path):
    log_path = tmp_path / "evidence.jsonl"
    dataset_path = tmp_path / "data" / "evidence_dataset" / "refusal_risk.parquet"
    model_a = tmp_path / "data" / "models" / "model_a.json"
    model_b = tmp_path / "data" / "models" / "model_b.json"
    _append_sample_log(log_path)
    build_report = build_refusal_risk_dataset(log_path, dataset_path)

    first = train_refusal_risk_model(dataset_path, model_a, seed=7)
    second = train_refusal_risk_model(dataset_path, model_b, seed=7)

    assert build_report.valid
    assert first.rows == 3
    assert first.metrics == second.metrics
    assert first.feature_weights == second.feature_weights
    artifact = json.loads(model_a.read_text(encoding="utf-8"))
    assert artifact["runtime_integration"] == "offline_only"
    assert isinstance(artifact["metrics"]["accuracy"], float)
