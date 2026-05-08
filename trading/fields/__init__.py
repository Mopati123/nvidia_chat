"""Field diagnostics for the lawful-collapse Hamiltonian overlay."""

from .magnetoelectric_coupling import compute_magnetoelectric_coupling
from .maxwell_tensor import compute_maxwell_tensor
from .minkowski_causality import check_causal_reach
from .polarity_detector import detect_polarity

__all__ = [
    "check_causal_reach",
    "compute_magnetoelectric_coupling",
    "compute_maxwell_tensor",
    "detect_polarity",
]
