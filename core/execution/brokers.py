"""Rootfile adapter for broker execution clients."""

from trading.brokers.deriv_broker import DerivBroker, DerivOrder
from trading.brokers.mt5_broker import MT5Broker, MT5Order

META = {
    "tier": "rootfile",
    "layer": "core.execution",
    "operator_type": "broker_adapter",
}

__all__ = ["DerivBroker", "DerivOrder", "MT5Broker", "MT5Order"]

