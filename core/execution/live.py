"""Rootfile adapter for Telegram live-trading execution."""

from apps.telegram.trading_live import LiveTradingSystem, live_trading

META = {
    "tier": "rootfile",
    "layer": "core.execution",
    "operator_type": "live_execution_adapter",
}

__all__ = ["LiveTradingSystem", "live_trading"]

