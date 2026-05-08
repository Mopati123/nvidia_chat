"""Unified H13 evidence facade."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.meta import OperatorMeta
from tachyonic_chain.audit_log import append_execution_evidence


META = OperatorMeta(
    tier="rootfile",
    layer="core.orchestration",
    operator_type="evidence_facade",
    canonical_law="H13",
)


@dataclass
class EvidenceEvent:
    """Canonical evidence event accepted by the facade."""

    event_type: str
    execution_id: str
    operation: str
    payload: Dict[str, Any] = field(default_factory=dict)
    symbol: Optional[str] = None
    outcome: str = "recorded"
    token_status: str = "not_applicable"


def _external_anchor_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return optional external anchor status without blocking pipeline work."""
    if os.getenv("ENABLE_ANCHORING", "0") != "1":
        return {"anchor_status": "disabled"}
    endpoint = os.getenv("APEX_ANCHOR_ENDPOINT", "").strip()
    if not endpoint:
        return {"anchor_status": "failed", "anchor_error": "missing_endpoint"}
    # Network anchoring is deliberately not performed in this offline-safe adapter.
    return {"anchor_status": "configured", "anchor_endpoint": endpoint, "anchor_txid": None}


def emit_evidence(event: EvidenceEvent, *, log_path: str | None = None) -> str:
    """Append runtime evidence and include optional non-blocking anchor status."""
    payload = dict(event.payload)
    payload.update(_external_anchor_status(payload))
    return append_execution_evidence(
        event_type=event.event_type,
        execution_id=event.execution_id,
        operation=event.operation,
        symbol=event.symbol,
        outcome=event.outcome,
        token_status=event.token_status,
        payload=payload,
        log_path=log_path,
    )
