"""Canonical simulation and proposal-generation adapters."""

from trading.path_integral.trajectory_generator import PathIntegralEngine

META = {
    "tier": "rootfile",
    "layer": "core.simulation",
    "operator_type": "simulation_adapter",
}

__all__ = ["PathIntegralEngine"]

