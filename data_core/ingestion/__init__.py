"""Data ingestion adapters."""

from trading.brokers.market_data import MarketDataFeed, market_feed

META = {
    "tier": "rootfile",
    "layer": "data_core.ingestion",
    "operator_type": "state_prep",
}

__all__ = ["MarketDataFeed", "market_feed"]

