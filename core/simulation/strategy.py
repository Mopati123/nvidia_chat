"""Rootfile adapter for strategy and proposal logic."""

META = {
    "tier": "rootfile",
    "layer": "core.simulation",
    "operator_type": "strategy_adapter",
}

try:
    from trading.agents.strategy_agent import StrategyAgent
except ImportError:
    StrategyAgent = None

__all__ = ["StrategyAgent"]

