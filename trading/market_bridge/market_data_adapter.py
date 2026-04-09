"""
market_data_adapter.py — High-level market data adapter

Re-export from minkowski_adapter for compatibility
"""

from .minkowski_adapter import MarketDataAdapter, MinkowskiAdapter, MarketTuple

__all__ = ['MarketDataAdapter', 'MinkowskiAdapter', 'MarketTuple']
