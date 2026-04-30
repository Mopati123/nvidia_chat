"""Canonical order-book analytics adapter."""

from trading.microstructure.order_book import (
    OrderBookEngine,
    OrderBookLevel,
    OrderBookSignals,
    OrderBookSnapshot,
)

META = {
    "tier": "rootfile",
    "layer": "core.simulation",
    "operator_type": "order_book_adapter",
}

__all__ = [
    "OrderBookEngine",
    "OrderBookLevel",
    "OrderBookSignals",
    "OrderBookSnapshot",
]
