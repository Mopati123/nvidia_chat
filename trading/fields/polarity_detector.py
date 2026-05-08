"""Wave polarity diagnostics from the field tensor."""

from __future__ import annotations

from typing import Dict


def detect_polarity(field_tensor: Dict) -> Dict[str, str | float]:
    """Infer coarse polarity and phase from electric impulse."""
    impulse = float(field_tensor.get("electric_impulse", 0.0) or 0.0)
    if impulse > 0:
        polarity = "positive"
        phase = "expansion"
    elif impulse < 0:
        polarity = "negative"
        phase = "contraction"
    else:
        polarity = "neutral"
        phase = "flat"
    return {
        "polarity": polarity,
        "phase": phase,
        "impulse": impulse,
    }
