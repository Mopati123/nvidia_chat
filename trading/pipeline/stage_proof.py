"""Deterministic proof helpers for pipeline stage history."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from core.meta import OperatorMeta

from .stage_contracts import StageOperatorSpec


META = OperatorMeta(
    tier="rootfile",
    layer="trading.pipeline",
    operator_type="stage_proof",
    canonical_law="H13",
)


REDACTED = "[REDACTED]"
SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "key",
    "password",
    "private",
    "secret",
    "signature",
    "token",
)


CONTEXT_PROOF_FIELDS = (
    "symbol",
    "timestamp",
    "source",
    "raw_data",
    "market_state",
    "ict_geometry",
    "geometry_data",
    "field_data",
    "field_admissible",
    "field_reason",
    "trajectories",
    "path_families",
    "path_signatures",
    "admissible_paths",
    "action_scores",
    "selected_path",
    "proposal",
    "collapse_decision",
    "execution_token",
    "execution_result",
    "reconciliation_status",
    "evidence_hash",
    "qpt_token_id",
    "weight_update_result",
    "risk_check_passed",
    "risk_check_message",
    "entropy_gate_passed",
    "entropy_gate_message",
    "action_weights",
)


def _secret_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(fragment in normalized for fragment in SECRET_KEY_FRAGMENTS)


def canonical_snapshot(value: Any) -> Any:
    """Return a JSON-safe, redacted, deterministically ordered snapshot."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "sha256": hashlib.sha256(value).hexdigest(),
            "length": len(value),
        }
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda item: str(item[0]))
        return {
            str(key): REDACTED if _secret_key(key) else canonical_snapshot(child)
            for key, child in items
        }
    if isinstance(value, (list, tuple)):
        return [canonical_snapshot(child) for child in value]
    if isinstance(value, set):
        children = [canonical_snapshot(child) for child in value]
        return sorted(children, key=lambda child: json.dumps(child, sort_keys=True, default=str))
    if is_dataclass(value) and not isinstance(value, type):
        return canonical_snapshot(asdict(value))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return canonical_snapshot(to_dict())
        except Exception:
            return {"type": value.__class__.__name__}
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return canonical_snapshot(item())
        except Exception:
            return {"type": value.__class__.__name__}
    shape = getattr(value, "shape", None)
    tolist = getattr(value, "tolist", None)
    if shape is not None and callable(tolist):
        try:
            return canonical_snapshot(tolist())
        except Exception:
            return {"type": value.__class__.__name__, "shape": str(shape)}
    return {"type": value.__class__.__name__}


def stable_hash(value: Any) -> str:
    """Hash a canonical snapshot with stable JSON encoding."""
    payload = json.dumps(
        canonical_snapshot(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stage_history_snapshot(context: Any) -> list[dict[str, Any]]:
    history = []
    for result in getattr(context, "stage_history", []) or []:
        stage = getattr(result, "stage", "")
        history.append({
            "stage": getattr(stage, "value", str(stage)),
            "success": bool(getattr(result, "success", False)),
            "canonical_law": getattr(result, "canonical_law", ""),
            "operator_id": getattr(result, "operator_id", ""),
            "proof_hash": getattr(result, "proof_hash", ""),
            "checkpoint_hash": getattr(result, "checkpoint_hash", ""),
            "refusal_code": getattr(result, "refusal_code", None),
        })
    return history


def stage_context_snapshot(context: Any) -> dict[str, Any]:
    """Capture the proof-relevant portion of a pipeline context."""
    snapshot = {
        field: getattr(context, field, None)
        for field in CONTEXT_PROOF_FIELDS
    }
    snapshot["stage_history"] = _stage_history_snapshot(context)
    return canonical_snapshot(snapshot)


def _code_fragment(value: Any) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96] or "unspecified"


def extract_refusal_code(stage: str, success: bool, output: Any, error: str | None) -> str | None:
    """Extract a compact refusal or failure code from stage output."""
    if not success:
        return f"{stage}:error:{_code_fragment(error or 'stage_failed')}"
    if not isinstance(output, Mapping):
        return None

    decision = str(output.get("decision") or output.get("collapse_decision") or "").upper()
    if decision == "REFUSED":
        return f"{stage}:refused:{_code_fragment(output.get('reason', 'scheduler_refused'))}"

    status = str(output.get("status") or output.get("outcome") or "").lower()
    if status in {"refused", "rejected", "blocked", "failed"}:
        return f"{stage}:{status}:{_code_fragment(output.get('reason', status))}"

    if output.get("admissible") is False:
        return f"{stage}:inadmissible:{_code_fragment(output.get('reason', 'admissibility_failed'))}"

    if output.get("entropy_gate_passed") is False or output.get("passed") is False:
        reason = output.get("entropy_reason") or output.get("reason") or "gate_failed"
        return f"{stage}:refused:{_code_fragment(reason)}"

    return None


def build_stage_proof(
    *,
    stage: str,
    spec: StageOperatorSpec,
    input_snapshot: Any,
    output_snapshot: Any,
    success: bool,
    output: Any,
    error: str | None,
    previous_hash: str,
) -> dict[str, Any]:
    """Build linked proof metadata for one stage result."""
    input_hash = stable_hash(input_snapshot)
    output_hash = stable_hash(output_snapshot)
    refusal_code = extract_refusal_code(stage, success, output, error)
    proof_payload = {
        "stage": stage,
        "operator_id": spec.operator_id,
        "canonical_law": spec.canonical_law,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "previous_hash": previous_hash,
        "success": success,
        "refusal_code": refusal_code,
    }
    return {
        **proof_payload,
        "proof_hash": stable_hash(proof_payload),
        "preconditions": list(spec.preconditions),
        "postconditions": list(spec.postconditions),
    }
