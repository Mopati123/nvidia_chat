"""Canonical rootfile law manifest for the lawful-collapse runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple


@dataclass(frozen=True)
class RootfileLaw:
    """One canonical law and its repository jurisdiction."""

    law_id: str
    name: str
    directory: str
    description: str
    invariants: Tuple[str, ...]
    allowed_couplings: Tuple[str, ...] = ()


ROOT = Path(__file__).resolve().parents[1]


LAWS: Dict[str, RootfileLaw] = {
    "H1": RootfileLaw(
        "H1",
        "State Space",
        "trading/pipeline",
        "Raw market data becomes typed runtime state.",
        ("state_exists_before_execution",),
        ("H2", "H5"),
    ),
    "H2": RootfileLaw(
        "H2",
        "Geometry",
        "trading/geometry",
        "Liquidity structure becomes metric geometry.",
        ("geometry_is_derived_from_state",),
        ("H3", "H4", "H5"),
    ),
    "H3": RootfileLaw(
        "H3",
        "Connection",
        "trading/geometry",
        "Liquidity gradients bend trajectory evolution.",
        ("connection_depends_on_metric_derivatives",),
        ("H4", "H5"),
    ),
    "H4": RootfileLaw(
        "H4",
        "Curvature",
        "trading/geometry",
        "Curvature classifies market regime stress.",
        ("curvature_reports_regime_stress",),
        ("H5", "H7"),
    ),
    "H5": RootfileLaw(
        "H5",
        "Path Space",
        "trading/path_integral",
        "Possible market futures are generated as candidate paths.",
        ("future_paths_precede_selection",),
        ("H6", "H7", "H8"),
    ),
    "H6": RootfileLaw(
        "H6",
        "Ramanujan Compression",
        "trading/pipeline",
        "Candidate paths compress into deterministic behavior families.",
        ("path_families_are_deterministic",),
        ("H7", "H8"),
    ),
    "H7": RootfileLaw(
        "H7",
        "Action",
        "trading/action",
        "Paths receive weighted cost and action scores.",
        ("action_scores_are_deterministic",),
        ("H8", "H9"),
    ),
    "H8": RootfileLaw(
        "H8",
        "Admissibility",
        "trading/risk",
        "Forbidden proposals are refused before collapse.",
        ("forbidden_paths_do_not_reach_scheduler",),
        ("H9", "H10"),
    ),
    "H9": RootfileLaw(
        "H9",
        "Entropy",
        "trading/pipeline",
        "Information gain is measured before scheduler authority.",
        ("entropy_gate_precedes_scheduler",),
        ("H10",),
    ),
    "H10": RootfileLaw(
        "H10",
        "Scheduler Authority",
        "core/orchestration",
        "Only scheduler authority may issue execution tokens.",
        ("no_operator_self_authorizes_collapse",),
        ("H11", "H13"),
    ),
    "H11": RootfileLaw(
        "H11",
        "Collapse Execution",
        "core/execution",
        "Authorized proposals become controlled side effects.",
        ("execution_requires_valid_token",),
        ("H12", "H13"),
    ),
    "H12": RootfileLaw(
        "H12",
        "Reconciliation",
        "trading/feedback",
        "Broker reality reconciles intended and realized state.",
        ("realized_outcomes_drive_feedback",),
        ("H13",),
    ),
    "H13": RootfileLaw(
        "H13",
        "Evidence",
        "tachyonic_chain",
        "Every collapse or refusal leaves verifiable evidence.",
        ("evidence_is_hash_chained",),
        (),
    ),
}


def get_law(law_id: str) -> RootfileLaw:
    """Return law metadata for a canonical law id."""
    normalized = law_id.strip().upper()
    if normalized not in LAWS:
        raise KeyError(f"Unknown rootfile law: {law_id}")
    return LAWS[normalized]


def get_law_dir(law_id: str) -> Path:
    """Return the repository directory that owns a canonical law."""
    return ROOT / get_law(law_id).directory


def validate_manifest_paths(root: Path | None = None) -> list[str]:
    """Return missing manifest directories, if any."""
    base = root or ROOT
    missing = []
    for law in LAWS.values():
        if not (base / law.directory).exists():
            missing.append(f"{law.law_id}:{law.directory}")
    return missing
