"""Rootfile adapter for path-integral proposal generation."""

from trading.path_integral.trajectory_generator import *  # noqa: F401,F403

META = {
    "tier": "rootfile",
    "layer": "core.simulation",
    "operator_type": "proposal_generator",
}

