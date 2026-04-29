"""Scoped HFT execution-token primitives.

The scheduler is the only component that should call the private mint helper.
Execution boundaries validate these tokens with operation="hft_execution".
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict

META = {
    "tier": "rootfile",
    "layer": "core.authority",
    "operator_type": "authority_token",
}


@dataclass(frozen=True)
class HFTExecutionScope:
    """Narrow authority envelope for one sandbox HFT execution burst."""

    broker: str
    symbol: str
    side: str
    max_notional: float
    max_slippage_bps: float
    max_order_count: int
    ttl_seconds: float
    strategy_id: str
    sandbox_only: bool = True

    def normalized(self) -> Dict[str, Any]:
        return {
            "broker": self.broker.lower(),
            "symbol": self.symbol.upper(),
            "side": self.side.lower(),
            "max_notional": float(self.max_notional),
            "max_slippage_bps": float(self.max_slippage_bps),
            "max_order_count": int(self.max_order_count),
            "ttl_seconds": float(self.ttl_seconds),
            "strategy_id": self.strategy_id,
            "sandbox_only": bool(self.sandbox_only),
        }


@dataclass(frozen=True)
class HFTExecutionToken:
    """Scheduler-issued token for sandbox HFT order attempts."""

    token_id: str
    timestamp: float
    expiry: float
    scope: HFTExecutionScope
    authorization_signature: str
    operation: str = "hft_execution"

    def expired(self) -> bool:
        return time.time() > self.expiry

    def verify(self) -> bool:
        return self.authorization_signature == _signature(
            self.token_id,
            self.timestamp,
            self.expiry,
            self.scope,
            self.operation,
        )

    def is_valid(self) -> bool:
        return self.verify() and not self.expired()

    @property
    def allowed_operators(self) -> list[str]:
        return [self.operation]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "timestamp": self.timestamp,
            "expiry": self.expiry,
            "operation": self.operation,
            "scope": asdict(self.scope),
        }


def _signature(
    token_id: str,
    timestamp: float,
    expiry: float,
    scope: HFTExecutionScope,
    operation: str,
) -> str:
    payload = {
        "token_id": token_id,
        "timestamp": timestamp,
        "expiry": expiry,
        "operation": operation,
        "scope": scope.normalized(),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _mint_hft_execution_token(scope: HFTExecutionScope) -> HFTExecutionToken:
    """Mint an HFT token. Intended for Scheduler.issue_hft_execution_token only."""
    timestamp = time.time()
    expiry = timestamp + float(scope.ttl_seconds)
    token_id_seed = json.dumps(scope.normalized(), sort_keys=True) + f":{timestamp}"
    token_id = hashlib.sha256(token_id_seed.encode("utf-8")).hexdigest()[:16]
    operation = "hft_execution"
    return HFTExecutionToken(
        token_id=token_id,
        timestamp=timestamp,
        expiry=expiry,
        scope=scope,
        authorization_signature=_signature(token_id, timestamp, expiry, scope, operation),
        operation=operation,
    )

