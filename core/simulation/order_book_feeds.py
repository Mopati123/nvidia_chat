"""Canonical read-only order-book feed adapters."""

from trading.microstructure.feeds import (
    BinanceDepthFeed,
    FeedHealth,
    FeedSnapshotError,
    FakeOrderBookFeed,
    IBDepthFeed,
    InteractiveBrokersDepthFeed,
    OrderBookFeed,
    ReplayOrderBookFeed,
)

META = {
    "tier": "rootfile",
    "layer": "core.simulation",
    "operator_type": "order_book_feed_adapter",
}

__all__ = [
    "BinanceDepthFeed",
    "FeedHealth",
    "FeedSnapshotError",
    "FakeOrderBookFeed",
    "IBDepthFeed",
    "InteractiveBrokersDepthFeed",
    "OrderBookFeed",
    "ReplayOrderBookFeed",
]

