"""Domain adapter: raw market data → operator space"""

from .minkowski_adapter import (
    MarketTuple,
    MinkowskiAdapter,
    MarketDataAdapter,
)

__all__ = [
    'MarketTuple',
    'MinkowskiAdapter',
    'MarketDataAdapter',
]
