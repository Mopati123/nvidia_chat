"""Minkowski-style causal reach checks for proposal displacement."""

from __future__ import annotations

from typing import Dict


def check_causal_reach(proposal: Dict, field_tensor: Dict, *, liquidity_speed: float = 1.0) -> Dict:
    """Return whether a proposal displacement is reachable under the field."""
    entry = float(proposal.get("entry", 0.0) or 0.0)
    target = float(proposal.get("target", entry) or entry)
    displacement = abs(target - entry)
    magnetic = abs(float(field_tensor.get("magnetic_liquidity", 0.0) or 0.0))
    electric = abs(float(field_tensor.get("electric_impulse", 0.0) or 0.0))
    reach = max(magnetic * float(liquidity_speed), electric, 1e-12)
    causal = displacement <= reach * 10.0
    return {
        "causal": causal,
        "displacement": displacement,
        "causal_reach": reach * 10.0,
        "reason": "causal" if causal else "causal_violation",
    }
