"""Broker-neutral H12 reconciliation facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.meta import OperatorMeta


META = OperatorMeta(
    tier="rootfile",
    layer="core.orchestration",
    operator_type="reconciliation_facade",
    canonical_law="H12",
)


@dataclass
class ReconciliationReport:
    """Canonical reconciliation summary consumed by QPT/evidence layers."""

    broker: str
    accepted: bool
    status: str
    realized_pnl: float | None = None
    evidence_valid: bool = False
    admissible: bool = False
    information_gain: float = 0.0
    scheduler_authorized: bool = False
    execution_id: str = ""
    symbol: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


def summarize_settlement_report(broker: str, report: Any) -> ReconciliationReport:
    """Convert existing MT5/Deriv settlement report objects into a canonical report."""
    records: List[Any] = list(getattr(report, "records", []) or [])
    closed = [record for record in records if getattr(record, "status", "") == "closed"]
    realized = [getattr(record, "realized_pnl", None) for record in closed]
    realized_values = [float(value) for value in realized if value is not None]
    return ReconciliationReport(
        broker=broker,
        accepted=bool(closed),
        status="accepted" if closed else "no_closed_records",
        realized_pnl=sum(realized_values) if realized_values else None,
        payload={
            "record_count": len(records),
            "closed_count": len(closed),
        },
    )
