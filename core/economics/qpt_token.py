"""Disabled-by-default QPT minting for accepted lawful-collapse reports."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

from core.meta import OperatorMeta
from core.orchestration.reconciliation import ReconciliationReport


META = OperatorMeta(
    tier="rootfile",
    layer="core.economics",
    operator_type="qpt_minter",
    canonical_law="H12",
)


def _ledger_path() -> Path:
    return Path(os.getenv("APEX_QPT_LEDGER", "data/qpt_ledger.jsonl"))


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _eligible(report: ReconciliationReport) -> bool:
    threshold = float(os.getenv("QPT_INFORMATION_GAIN_THRESHOLD", "0.0") or 0.0)
    return (
        report.accepted
        and report.admissible
        and report.information_gain >= threshold
        and report.scheduler_authorized
        and report.evidence_valid
    )


def mint_qpt_if_applicable(report: ReconciliationReport) -> Optional[str]:
    """Persist a local QPT token ID only when all collapse proof gates pass."""
    if os.getenv("ENABLE_QPT", "0") != "1":
        return None
    if not _eligible(report):
        return None

    timestamp = time.time()
    identity = {
        "broker": report.broker,
        "execution_id": report.execution_id,
        "information_gain": report.information_gain,
        "realized_pnl": report.realized_pnl,
        "status": report.status,
        "symbol": report.symbol,
        "timestamp": timestamp,
    }
    token_id = "qpt_" + hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    _append_jsonl(
        _ledger_path(),
        {
            "token_id": token_id,
            **identity,
            "conditions": {
                "admissible": report.admissible,
                "evidence_valid": report.evidence_valid,
                "reconciliation_accepted": report.accepted,
                "scheduler_authorized": report.scheduler_authorized,
            },
        },
    )
    return token_id
