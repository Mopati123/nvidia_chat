"""Durable hash-chained execution evidence log."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

META = {
    "tier": "rootfile",
    "layer": "tachyonic_chain",
    "operator_type": "audit_log",
}


DEFAULT_EVIDENCE_LOG = Path("logs") / "execution_evidence.jsonl"


def _canonical_hash(payload: Dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _last_record_hash(path: Path) -> str:
    if not path.exists():
        return hashlib.sha256(b"GENESIS").hexdigest()

    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size == 0:
                return hashlib.sha256(b"GENESIS").hexdigest()

            offset = min(size, 8192)
            handle.seek(-offset, os.SEEK_END)
            lines = handle.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return hashlib.sha256(b"GENESIS").hexdigest()

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            return str(json.loads(line).get("record_hash", ""))
        except json.JSONDecodeError:
            break
    return hashlib.sha256(b"GENESIS").hexdigest()


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
    path = Path(log_path or os.getenv("APEX_EVIDENCE_LOG", DEFAULT_EVIDENCE_LOG))
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
