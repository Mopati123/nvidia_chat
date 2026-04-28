"""Durable hash-chained execution evidence log."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

META = {
    "tier": "rootfile",
    "layer": "tachyonic_chain",
    "operator_type": "audit_log",
}


DEFAULT_EVIDENCE_LOG = Path("logs") / "execution_evidence.jsonl"
GENESIS_HASH = hashlib.sha256(b"GENESIS").hexdigest()


@dataclass
class ValidationIssue:
    """A single audit-chain validation issue."""

    path: str
    message: str
    line: Optional[int] = None


@dataclass
class ValidationReport:
    """Validation result for an execution evidence log."""

    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)


def _canonical_hash(payload: Dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _resolve_log_path(log_path: Optional[str | Path] = None) -> Path:
    return Path(log_path or os.getenv("APEX_EVIDENCE_LOG", DEFAULT_EVIDENCE_LOG))


def _last_record_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS_HASH

    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size == 0:
                return GENESIS_HASH

            offset = min(size, 8192)
            handle.seek(-offset, os.SEEK_END)
            lines = handle.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return GENESIS_HASH

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            return str(json.loads(line).get("record_hash", ""))
        except json.JSONDecodeError:
            break
    return GENESIS_HASH


def iter_execution_evidence(log_path: Optional[str | Path] = None) -> Iterator[Dict[str, Any]]:
    """Yield execution evidence records from a JSONL audit log."""
    path = _resolve_log_path(log_path)
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSON in {path} line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Audit record in {path} line {line_number} is not an object")
            yield record


def verify_execution_evidence_chain(log_path: Optional[str | Path] = None) -> ValidationReport:
    """Validate record hashes and previous-hash links for a JSONL evidence log."""
    path = _resolve_log_path(log_path)
    issues: List[ValidationIssue] = []
    if not path.exists() or path.stat().st_size == 0:
        return ValidationReport(True, issues)

    expected_previous = GENESIS_HASH
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                issues.append(ValidationIssue(str(path), f"malformed JSON: {exc}", line_number))
                continue

            if not isinstance(record, dict):
                issues.append(ValidationIssue(str(path), "record is not a JSON object", line_number))
                continue

            record_hash = record.get("record_hash")
            if not record_hash:
                issues.append(ValidationIssue(str(path), "missing record_hash", line_number))

            previous_hash = record.get("previous_hash")
            if previous_hash != expected_previous:
                issues.append(
                    ValidationIssue(
                        str(path),
                        f"previous_hash mismatch: expected {expected_previous}, got {previous_hash}",
                        line_number,
                    )
                )

            unsigned_record = dict(record)
            unsigned_record.pop("record_hash", None)
            computed_hash = _canonical_hash(unsigned_record)
            if record_hash != computed_hash:
                issues.append(
                    ValidationIssue(
                        str(path),
                        f"record_hash mismatch: expected {computed_hash}, got {record_hash}",
                        line_number,
                    )
                )

            expected_previous = str(record_hash or computed_hash)

    return ValidationReport(not issues, issues)


def append_execution_evidence(
    *,
    event_type: str,
    execution_id: str,
    outcome: str,
    operation: str,
    symbol: Optional[str] = None,
    token_status: Optional[str] = None,
    evidence_hash: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    log_path: Optional[str | Path] = None,
) -> str:
    """Append an execution/refusal record and return its hash-chain record hash."""
    path = _resolve_log_path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": time.time(),
        "event_type": event_type,
        "execution_id": execution_id,
        "operation": operation,
        "symbol": symbol,
        "outcome": outcome,
        "token_status": token_status,
        "evidence_hash": evidence_hash,
        "payload": payload or {},
        "previous_hash": _last_record_hash(path),
    }
    record["record_hash"] = _canonical_hash(record)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), default=str))
        handle.write("\n")

    return record["record_hash"]
