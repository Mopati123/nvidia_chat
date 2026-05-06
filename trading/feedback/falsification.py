"""Post-outcome falsification scoring for authorized and refused decisions."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from tachyonic_chain.audit_log import append_execution_evidence


AUTHORIZED_DECISIONS = {"authorized", "executed", "filled", "success"}
REFUSED_DECISIONS = {"refused", "blocked", "failed", "rejected"}


@dataclass
class FalsificationScore:
    """Classification of a decision after forward outcome is known."""

    decision: str
    classification: str
    correct: Optional[bool]
    symbol: Optional[str] = None
    broker: Optional[str] = None
    reference_id: Optional[str] = None
    realized_pnl: Optional[float] = None
    would_have_pnl: Optional[float] = None
    predicted_pnl: Optional[float] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    evidence_hash: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.pop("evidence_hash", None)
        payload["pnl_prediction"] = self.predicted_pnl
        return payload


def _maybe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_decision(
    decision: str,
    *,
    realized_pnl: Any = None,
    would_have_pnl: Any = None,
    predicted_pnl: Any = None,
    symbol: Optional[str] = None,
    broker: Optional[str] = None,
    reference_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> FalsificationScore:
    """Score an authorized or refused decision after forward outcome data exists."""
    normalized = str(decision or "").strip().lower()
    realized = _maybe_float(realized_pnl)
    hypothetical = _maybe_float(would_have_pnl)
    predicted = _maybe_float(predicted_pnl)

    if normalized in AUTHORIZED_DECISIONS:
        if realized is None:
            classification = "pending_authorization_outcome"
            correct = None
            reason = "authorized decision has no realized outcome yet"
        elif realized >= 0:
            classification = "correct_authorization"
            correct = True
            reason = "authorized decision closed non-negative"
        else:
            classification = "bad_authorization"
            correct = False
            reason = "authorized decision closed negative"
    elif normalized in REFUSED_DECISIONS:
        if hypothetical is None:
            classification = "unscored_refusal"
            correct = None
            reason = "refused decision has no forward outcome estimate"
        elif hypothetical < 0:
            classification = "avoided_loss"
            correct = True
            reason = "refusal avoided a negative forward outcome"
        elif hypothetical > 0:
            classification = "missed_opportunity"
            correct = False
            reason = "refusal skipped a positive forward outcome"
        else:
            classification = "correct_refusal"
            correct = True
            reason = "refusal avoided a neutral forward outcome"
    else:
        classification = "unscored_decision"
        correct = None
        reason = "decision type is not recognized for falsification scoring"

    return FalsificationScore(
        decision=str(decision),
        classification=classification,
        correct=correct,
        symbol=symbol,
        broker=broker,
        reference_id=str(reference_id) if reference_id is not None else None,
        realized_pnl=realized,
        would_have_pnl=hypothetical,
        predicted_pnl=predicted,
        reason=reason,
        metadata=metadata or {},
    )


def append_falsification_evidence(
    score: FalsificationScore,
    evidence_log_path: str | Path,
) -> str:
    """Append falsification scoring evidence without touching broker state."""
    reference = score.reference_id or f"{int(time.time())}"
    record_hash = append_execution_evidence(
        event_type="falsification_score",
        execution_id=f"falsification_{reference}",
        operation="forward_outcome_falsification",
        symbol=score.symbol,
        outcome=score.classification,
        token_status="post_outcome_verified" if score.correct is not None else "outcome_missing",
        payload=score.to_payload(),
        log_path=evidence_log_path,
    )
    score.evidence_hash = record_hash
    return record_hash
