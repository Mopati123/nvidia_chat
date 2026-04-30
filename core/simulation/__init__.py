"""Canonical simulation and proposal-generation adapters."""

from trading.path_integral.trajectory_generator import PathIntegralEngine
from trading.microstructure.order_book import OrderBookEngine, OrderBookSignals, OrderBookSnapshot

META = {
    "tier": "rootfile",
    "layer": "core.simulation",
    "operator_type": "simulation_adapter",
}

__all__ = [
    "PathIntegralEngine",
    "OrderBookEngine",
    "OrderBookSignals",
    "OrderBookSnapshot",
]
