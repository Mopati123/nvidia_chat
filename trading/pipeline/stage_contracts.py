"""Canonical pipeline stage contracts for rootfile proof generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.meta import OperatorMeta
from core.rootfile_manifest import LAWS


META = OperatorMeta(
    tier="rootfile",
    layer="trading.pipeline",
    operator_type="stage_contracts",
    canonical_law="H10",
)


@dataclass(frozen=True)
class StageOperatorSpec:
    """Governance metadata for one canonical pipeline stage."""

    stage: str
    operator_id: str
    canonical_law: str
    description: str
    preconditions: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    supporting_laws: tuple[str, ...] = ()


CANONICAL_STAGE_SEQUENCE: tuple[str, ...] = (
    "data_ingestion",
    "state_construction",
    "ict_extraction",
    "geometry_computation",
    "field_evaluation",
    "trajectory_generation",
    "ramanujan_compression",
    "admissibility_filtering",
    "action_evaluation",
    "path_integral",
    "interference_selection",
    "path_selection",
    "proposal_generation",
    "admissibility_check",
    "entropy_gate",
    "scheduler_collapse",
    "execution",
    "reconciliation",
    "evidence_emission",
    "weight_update",
)


def _spec(
    stage: str,
    law: str,
    description: str,
    *,
    preconditions: tuple[str, ...] = (),
    postconditions: tuple[str, ...] = (),
    supporting_laws: tuple[str, ...] = (),
) -> StageOperatorSpec:
    return StageOperatorSpec(
        stage=stage,
        operator_id=f"pipeline.{law.lower()}.{stage}",
        canonical_law=law,
        description=description,
        preconditions=preconditions,
        postconditions=postconditions,
        supporting_laws=supporting_laws,
    )


STAGE_OPERATOR_SPECS: Mapping[str, StageOperatorSpec] = {
    "data_ingestion": _spec(
        "data_ingestion",
        "H1",
        "Normalize raw input into the canonical pipeline context.",
        preconditions=("raw_data_present",),
        postconditions=("source_recorded",),
    ),
    "state_construction": _spec(
        "state_construction",
        "H1",
        "Build typed market state from bars, ticks, and optional order book data.",
        preconditions=("raw_data_present",),
        postconditions=("market_state_exists",),
    ),
    "ict_extraction": _spec(
        "ict_extraction",
        "H2",
        "Extract ICT and liquidity structure for downstream geometry.",
        preconditions=("market_state_exists",),
        postconditions=("ict_geometry_available",),
    ),
    "geometry_computation": _spec(
        "geometry_computation",
        "H2",
        "Convert liquidity context into metric, connection, and curvature diagnostics.",
        preconditions=("ict_geometry_available",),
        postconditions=("geometry_data_available",),
        supporting_laws=("H3", "H4"),
    ),
    "field_evaluation": _spec(
        "field_evaluation",
        "H8",
        "Evaluate field diagnostics before hard admissibility gates.",
        preconditions=("geometry_data_available",),
        postconditions=("field_admissibility_recorded",),
        supporting_laws=("H2", "H3", "H4"),
    ),
    "trajectory_generation": _spec(
        "trajectory_generation",
        "H5",
        "Generate candidate future paths from the current market geometry.",
        preconditions=("market_state_exists",),
        postconditions=("trajectories_available",),
    ),
    "ramanujan_compression": _spec(
        "ramanujan_compression",
        "H6",
        "Compress candidate futures into deterministic behavior families.",
        preconditions=("trajectories_available",),
        postconditions=("path_families_available",),
    ),
    "admissibility_filtering": _spec(
        "admissibility_filtering",
        "H8",
        "Filter impossible or forbidden paths before action scoring.",
        preconditions=("trajectories_available",),
        postconditions=("admissible_paths_available",),
    ),
    "action_evaluation": _spec(
        "action_evaluation",
        "H7",
        "Assign deterministic action costs to admissible paths.",
        preconditions=("admissible_paths_available",),
        postconditions=("action_scores_available",),
    ),
    "path_integral": _spec(
        "path_integral",
        "H7",
        "Convert action costs into path weights.",
        preconditions=("action_scores_available",),
        postconditions=("path_weights_available",),
    ),
    "interference_selection": _spec(
        "interference_selection",
        "H7",
        "Sharpen competing futures through interference selection.",
        preconditions=("path_weights_available",),
        postconditions=("interference_selection_recorded",),
    ),
    "path_selection": _spec(
        "path_selection",
        "H7",
        "Select the least-action path candidate.",
        preconditions=("admissible_paths_available",),
        postconditions=("selected_path_available",),
    ),
    "proposal_generation": _spec(
        "proposal_generation",
        "H8",
        "Convert the selected path into a trade proposal without execution authority.",
        preconditions=("selected_path_available",),
        postconditions=("proposal_available",),
    ),
    "admissibility_check": _spec(
        "admissibility_check",
        "H8",
        "Apply risk and admissibility gates before scheduler authority.",
        preconditions=("proposal_available",),
        postconditions=("risk_check_recorded",),
    ),
    "entropy_gate": _spec(
        "entropy_gate",
        "H9",
        "Measure information gain before scheduler collapse.",
        preconditions=("risk_check_recorded",),
        postconditions=("entropy_gate_recorded",),
    ),
    "scheduler_collapse": _spec(
        "scheduler_collapse",
        "H10",
        "Authorize or refuse collapse and issue execution authority when lawful.",
        preconditions=("risk_check_passed", "entropy_gate_passed"),
        postconditions=("collapse_decision_recorded",),
    ),
    "execution": _spec(
        "execution",
        "H11",
        "Execute only with valid scheduler-issued authority.",
        preconditions=("collapse_authorized",),
        postconditions=("execution_result_recorded",),
    ),
    "reconciliation": _spec(
        "reconciliation",
        "H12",
        "Compare intended execution state with realized outcome state.",
        preconditions=("execution_result_recorded",),
        postconditions=("reconciliation_recorded",),
    ),
    "evidence_emission": _spec(
        "evidence_emission",
        "H13",
        "Emit verifiable evidence for the observed run.",
        preconditions=("collapse_decision_recorded",),
        postconditions=("evidence_hash_recorded",),
    ),
    "weight_update": _spec(
        "weight_update",
        "H12",
        "Feed reconciled outcome signal into the learning layer when enabled.",
        preconditions=("reconciliation_recorded",),
        postconditions=("weight_update_recorded",),
        supporting_laws=("H13",),
    ),
    "completed": _spec(
        "completed",
        "H13",
        "Close the proof chain for a completed pipeline observation.",
        preconditions=("stage_history_available",),
        postconditions=("terminal_proof_recorded",),
    ),
    "failed": _spec(
        "failed",
        "H13",
        "Close the proof chain for a failed pipeline observation.",
        preconditions=("stage_history_available",),
        postconditions=("terminal_proof_recorded",),
    ),
}


def get_stage_operator_spec(stage: Any) -> StageOperatorSpec:
    """Return the operator contract for a stage enum, string, or stage-like object."""
    stage_value = str(getattr(stage, "value", stage))
    try:
        return STAGE_OPERATOR_SPECS[stage_value]
    except KeyError as exc:
        raise KeyError(f"Unknown pipeline stage contract: {stage_value}") from exc


def validate_stage_operator_specs() -> list[str]:
    """Return contract validation issues, if any."""
    issues: list[str] = []
    for stage in (*CANONICAL_STAGE_SEQUENCE, "completed", "failed"):
        spec = STAGE_OPERATOR_SPECS.get(stage)
        if spec is None:
            issues.append(f"missing stage spec: {stage}")
            continue
        laws = (spec.canonical_law, *spec.supporting_laws)
        for law in laws:
            if law not in LAWS:
                issues.append(f"{stage} declares unknown law: {law}")
    extras = sorted(set(STAGE_OPERATOR_SPECS) - set(CANONICAL_STAGE_SEQUENCE) - {"completed", "failed"})
    issues.extend(f"unexpected stage spec: {stage}" for stage in extras)
    return issues
