"""Magnetoelectric coupling diagnostics for field admissibility."""

from __future__ import annotations

from typing import Dict


def compute_magnetoelectric_coupling(field_tensor: Dict) -> Dict[str, float]:
    """Compute D/H style coupling values from field components."""
    electric = float(field_tensor.get("electric_impulse", 0.0) or 0.0)
    magnetic = float(field_tensor.get("magnetic_liquidity", 0.0) or 0.0)
    displacement_field = electric + 0.5 * magnetic
    magnetic_field = magnetic - 0.5 * electric
    coupling_strength = abs(electric * magnetic)
    return {
        "D": displacement_field,
        "H": magnetic_field,
        "coupling_strength": coupling_strength,
    }
