"""Rootfile adapter for Riemannian market geometry."""

META = {
    "tier": "rootfile",
    "layer": "core.simulation",
    "operator_type": "observable_adapter",
}

try:
    from trading.geometry.connection import *  # noqa: F401,F403
    from trading.geometry.curvature import *  # noqa: F401,F403
    from trading.geometry.geodesic import *  # noqa: F401,F403
    from trading.geometry.liquidity_field import *  # noqa: F401,F403
    from trading.geometry.metric import *  # noqa: F401,F403
except ImportError:
    # Geometry submodules can be imported directly when a narrower surface is needed.
    pass

