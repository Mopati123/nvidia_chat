"""Build sanitized ML datasets from execution evidence logs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq

from tachyonic_chain.audit_log import (
    iter_execution_evidence,
    verify_execution_evidence_chain,
)

META = {
    "tier": "rootfile",
    "layer": "data_core.ml",
    "operator_type": "cp_map",
}


DATASET_SCHEMA = pa.schema([
    ("timestamp", pa.float64()),
    ("hour_utc", pa.int64()),
    ("day_of_week", pa.int64()),
    ("event_type", pa.string()),
    ("operation", pa.string()),
    ("symbol_bucket", pa.string()),
    ("outcome", pa.string()),
    ("token_status", pa.string()),
    ("evidence_hash", pa.string()),
    ("record_hash", pa.string()),
    ("previous_hash", pa.string()),
    ("broker", pa.string()),
    ("direction", pa.string()),
    ("mode", pa.string()),
    ("reason", pa.string()),
    ("volume", pa.float64()),
    ("amount", pa.float64()),
    ("execution_time_ms", pa.float64()),
    ("pnl_prediction", pa.float64()),
    ("retcode", pa.int64()),
    ("risk_label", pa.int64()),
])

DATASET_COLUMNS = [field.name for field in DATASET_SCHEMA]
SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "private",
    "credential",
    "credentials",
    "account",
    "login",
    "server",
    "token",
)
SAFE_TOKEN_FIELDS = {"token_status"}


@dataclass
class DatasetBuildReport:
    """Summary returned after building a refusal/risk dataset."""

    valid: bool
    rows: int
    output_path: str
    issues: List[str] = field(default_factory=list)


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    if lower in SAFE_TOKEN_FIELDS:
        return False
    return any(fragment in lower for fragment in SENSITIVE_KEY_FRAGMENTS)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _symbol_bucket(symbol: Any) -> str:
    value = str(symbol or "").upper()
    if not value:
        return "unknown"
    if "BTC" in value or "ETH" in value or value.startswith("CRY"):
        return "crypto"
    if value.startswith("R_") or "VOLATILITY" in value:
        return "synthetic"
    if len(value) == 6 and value.isalpha():
        return "forex"
    return "other"


def _timestamp_parts(timestamp: Any) -> tuple[float, int, int]:
    ts = _coerce_float(timestamp) or 0.0
    if ts <= 0:
        return ts, -1, -1
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return ts, dt.hour, dt.weekday()


def _payload(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def _safe_payload_value(payload: Dict[str, Any], key: str) -> Any:
    if _is_sensitive_key(key):
        return None
    return payload.get(key)


def _risk_label(record: Dict[str, Any]) -> int:
    outcome = str(record.get("outcome") or "").lower()
    token_status = str(record.get("token_status") or "").lower()
    event_type = str(record.get("event_type") or "").lower()
    risky_tokens = ("missing", "invalid", "expired", "refused", "unauthorized")
    if outcome in {"refused", "failed", "blocked", "error"}:
        return 1
    if any(marker in token_status for marker in risky_tokens):
        return 1
    if "refusal" in event_type or "refused" in event_type:
        return 1
    return 0


def sanitize_audit_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a secret-free, stable feature row from one audit record."""
    payload = _payload(record)
    timestamp, hour_utc, day_of_week = _timestamp_parts(record.get("timestamp"))

    sanitized = {
        "timestamp": timestamp,
        "hour_utc": hour_utc,
        "day_of_week": day_of_week,
        "event_type": _safe_string(record.get("event_type")),
        "operation": _safe_string(record.get("operation")),
        "symbol_bucket": _symbol_bucket(record.get("symbol")),
        "outcome": _safe_string(record.get("outcome")),
        "token_status": _safe_string(record.get("token_status")),
        "evidence_hash": _safe_string(record.get("evidence_hash")),
        "record_hash": _safe_string(record.get("record_hash")),
        "previous_hash": _safe_string(record.get("previous_hash")),
        "broker": _safe_string(_safe_payload_value(payload, "broker")),
        "direction": _safe_string(_safe_payload_value(payload, "direction") or _safe_payload_value(payload, "order_type")),
        "mode": _safe_string(_safe_payload_value(payload, "mode")),
        "reason": _safe_string(_safe_payload_value(payload, "reason")),
        "volume": _coerce_float(_safe_payload_value(payload, "volume")),
        "amount": _coerce_float(_safe_payload_value(payload, "amount")),
        "execution_time_ms": _coerce_float(_safe_payload_value(payload, "execution_time_ms")),
        "pnl_prediction": _coerce_float(_safe_payload_value(payload, "pnl_prediction")),
        "retcode": _coerce_int(_safe_payload_value(payload, "retcode")),
        "risk_label": _risk_label(record),
    }
    return {column: sanitized.get(column) for column in DATASET_COLUMNS}


def audit_record_to_refusal_example(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert one audit record to a refusal/risk example, or skip unsupported rows."""
    operation = str(record.get("operation") or "")
    if not operation:
        return None
    if record.get("outcome") is None and record.get("token_status") is None:
        return None
    return sanitize_audit_record(record)


def _write_parquet(rows: Iterable[Dict[str, Any]], output_path: Path) -> int:
    materialized = [{column: row.get(column) for column in DATASET_COLUMNS} for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if materialized:
        table = pa.Table.from_pylist(materialized, schema=DATASET_SCHEMA)
    else:
        table = pa.Table.from_arrays(
            [pa.array([], type=field.type) for field in DATASET_SCHEMA],
            schema=DATASET_SCHEMA,
        )
    pq.write_table(table, output_path)
    return len(materialized)


def build_refusal_risk_dataset(input_path: str | Path, output_path: str | Path) -> DatasetBuildReport:
    """Validate an evidence log and export sanitized refusal/risk examples."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    validation = verify_execution_evidence_chain(input_path)
    if not validation.valid:
        issues = [
            f"line {issue.line}: {issue.message}" if issue.line else issue.message
            for issue in validation.issues
        ]
        return DatasetBuildReport(False, 0, str(output_path), issues)

    rows = [
        example
        for record in iter_execution_evidence(input_path)
        if (example := audit_record_to_refusal_example(record)) is not None
    ]
    row_count = _write_parquet(rows, output_path)
    return DatasetBuildReport(True, row_count, str(output_path), [])


def read_refusal_risk_dataset(path: str | Path) -> List[Dict[str, Any]]:
    """Read a refusal/risk Parquet dataset into Python records."""
    table = pq.read_table(Path(path), schema=DATASET_SCHEMA)
    return table.to_pylist()
