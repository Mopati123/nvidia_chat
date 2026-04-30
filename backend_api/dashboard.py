"""Rootfile adapter for dashboard APIs."""

META = {
    "tier": "rootfile",
    "layer": "backend_api",
    "operator_type": "measurement_api",
}

try:
    from trading.dashboard.app import *  # noqa: F401,F403
except Exception:
    pass

