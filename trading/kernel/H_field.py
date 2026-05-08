"""Field Hamiltonian overlay for geometry-aware admissibility diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from core.meta import OperatorMeta
from trading.fields import (
    check_causal_reach,
    compute_magnetoelectric_coupling,
    compute_maxwell_tensor,
    detect_polarity,
)


META = OperatorMeta(
    tier="rootfile",
    layer="trading.kernel",
    operator_type="field_hamiltonian",
    canonical_law="H8",
)


@dataclass
class FieldEvaluation:
    """Result emitted by the field Hamiltonian."""

    field_tensor: Dict[str, float]
    polarity: Dict[str, str | float]
    causal_status: Dict
    coupling: Dict[str, float]
    field_admissible: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "field_tensor": self.field_tensor,
            "polarity": self.polarity,
            "causal_status": self.causal_status,
            "coupling": self.coupling,
            "field_admissible": self.field_admissible,
            "reasons": self.reasons,
        }


class FieldHamiltonian:
    """Combine field tensor, polarity, causality, and coupling into one gate."""

    def evaluate(self, market_state: Dict, geometry_data: Dict, proposal: Dict | None = None) -> FieldEvaluation:
        proposal = proposal or {}
        tensor = compute_maxwell_tensor(market_state, geometry_data)
        polarity = detect_polarity(tensor)
        causal = check_causal_reach(proposal, tensor) if proposal else {
            "causal": True,
            "displacement": 0.0,
            "causal_reach": 0.0,
            "reason": "no_proposal_yet",
        }
        coupling = compute_magnetoelectric_coupling(tensor)
        reasons = []
        if not causal.get("causal", False):
            reasons.append("causal_violation")
        if polarity.get("polarity") == "neutral" and coupling.get("coupling_strength", 0.0) == 0.0:
            reasons.append("flat_field")
        return FieldEvaluation(
            field_tensor=tensor,
            polarity=polarity,
            causal_status=causal,
            coupling=coupling,
            field_admissible=not reasons,
            reasons=reasons,
        )
