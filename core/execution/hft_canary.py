"""Code-gated real-routing shell for HFT canary deployment.

Real routing is refused by default. It requires explicit environment gates,
valid sandbox certification, non-sandbox HFT token scope, and the hard limits
from the HFT gateway.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from tachyonic_chain.audit_log import append_execution_evidence

from .hft import (
    HFTExecutionState,
    HFTOrderRequest,
    HFTOrderResult,
    HFTRiskLimits,
    HFTSandboxGateway,
)

META = {
    "tier": "rootfile",
    "layer": "core.execution",
    "operator_type": "hft_canary_gate",
}


DEFAULT_CERTIFICATION_PATH = Path("trading_data") / "hft" / "sandbox_certification.json"


@dataclass(frozen=True)
class CanaryConfig:
    """Environment-backed canary controls for real HFT routing."""

    allow_real_trading: bool = False
    hft_canary_enabled: bool = False
    sandbox_certification_path: str = str(DEFAULT_CERTIFICATION_PATH)
    max_notional: float = 10.0
    max_daily_loss: float = 5.0
    max_active_symbols: int = 1
    allowed_symbol: Optional[str] = None

    @classmethod
    def from_env(cls) -> "CanaryConfig":
        return cls(
            allow_real_trading=os.getenv("ALLOW_REAL_TRADING") == "1",
            hft_canary_enabled=os.getenv("HFT_CANARY_ENABLED") == "1",
            sandbox_certification_path=os.getenv(
                "HFT_SANDBOX_CERTIFICATION",
                str(DEFAULT_CERTIFICATION_PATH),
            ),
            max_notional=float(os.getenv("HFT_CANARY_MAX_NOTIONAL", "10.0")),
            max_daily_loss=float(os.getenv("HFT_CANARY_DAILY_LOSS_CAP", "5.0")),
            max_active_symbols=int(os.getenv("HFT_CANARY_MAX_ACTIVE_SYMBOLS", "1")),
            allowed_symbol=os.getenv("HFT_CANARY_SYMBOL"),
        )


@dataclass(frozen=True)
class SandboxCertification:
    """Certification record proving sandbox HFT tests passed."""

    passed: bool
    generated_at: float
    suite: str = "hft_sandbox"
    expires_at: Optional[float] = None

    @classmethod
    def from_file(cls, path: str | Path) -> "SandboxCertification":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            passed=bool(payload.get("passed")),
            generated_at=float(payload.get("generated_at", 0.0)),
            suite=str(payload.get("suite", "hft_sandbox")),
            expires_at=(
                float(payload["expires_at"])
                if payload.get("expires_at") is not None
                else None
            ),
        )

    def valid(self, *, now: Optional[float] = None) -> bool:
        now = now or time.time()
        if not self.passed:
            return False
        if self.suite != "hft_sandbox":
            return False
        if self.expires_at is not None and now > self.expires_at:
            return False
        return True


def write_sandbox_certification(path: str | Path, *, expires_in_seconds: float = 86400.0) -> str:
    """Write a local sandbox certification marker after tests pass."""
    now = time.time()
    payload = {
        "passed": True,
        "generated_at": now,
        "suite": "hft_sandbox",
        "expires_at": now + expires_in_seconds,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(target)


class CanaryGate:
    """Refusal-first gate for real HFT canary routing."""

    def __init__(self, config: Optional[CanaryConfig] = None) -> None:
        self.config = config or CanaryConfig.from_env()

    def refusal_reason(self, request: HFTOrderRequest, state: HFTExecutionState) -> Optional[str]:
        if request.sandbox:
            return "real_routing_requires_non_sandbox_request"
        if not self.config.allow_real_trading:
            return "real_trading_disabled"
        if not self.config.hft_canary_enabled:
            return "hft_canary_disabled"
        if not self._certification_valid():
            return "sandbox_certification_required"
        if request.notional > self.config.max_notional:
            return "canary_notional_limit_exceeded"
        if state.daily_pnl <= -abs(self.config.max_daily_loss):
            return "canary_daily_loss_cap_exceeded"
        if self.config.allowed_symbol and request.symbol.upper() != self.config.allowed_symbol.upper():
            return "canary_symbol_not_allowed"
        active_symbols = {symbol for symbol, notional in state.per_symbol_notional.items() if notional > 0}
        if request.symbol not in active_symbols and len(active_symbols) >= self.config.max_active_symbols:
            return "canary_active_symbol_limit_exceeded"
        return None

    def _certification_valid(self) -> bool:
        path = Path(self.config.sandbox_certification_path)
        if not path.exists():
            return False
        try:
            return SandboxCertification.from_file(path).valid()
        except Exception:
            return False


class BinanceHFTExecutionAdapter:
    """Thin Binance order adapter, invoked only after canary gates pass."""

    def __init__(self, client: Optional[Any] = None) -> None:
        self.client = client

    def place_order(self, request: HFTOrderRequest) -> Dict[str, Any]:
        if self.client is None:
            raise RuntimeError("binance client not configured")
        response = self.client.create_order(
            symbol=request.symbol,
            side=request.side.upper(),
            type="MARKET",
            quantity=request.quantity,
        )
        return {
            "order_id": str(response.get("orderId", response.get("clientOrderId", ""))),
            "status": response.get("status", "submitted"),
        }


class IBHFTExecutionAdapter:
    """Thin IB/TWS order adapter, invoked only after canary gates pass."""

    def __init__(self, client: Optional[Any] = None) -> None:
        self.client = client

    def place_order(self, request: HFTOrderRequest) -> Dict[str, Any]:
        if self.client is None:
            raise RuntimeError("ib client not configured")
        if not hasattr(self.client, "place_market_order"):
            raise RuntimeError("ib client must expose place_market_order")
        response = self.client.place_market_order(
            symbol=request.symbol,
            side=request.side.lower(),
            quantity=request.quantity,
        )
        return {
            "order_id": str(response.get("order_id", response.get("perm_id", ""))),
            "status": response.get("status", "submitted"),
        }


class CodeGatedHFTGateway:
    """Real-routing gateway that refuses until canary gates are satisfied."""

    def __init__(
        self,
        *,
        broker: Any,
        gate: Optional[CanaryGate] = None,
        limits: Optional[HFTRiskLimits] = None,
        state: Optional[HFTExecutionState] = None,
        evidence_log: Optional[str] = None,
    ) -> None:
        self.gate = gate or CanaryGate()
        self.gateway = HFTSandboxGateway(
            broker=broker,
            limits=limits,
            state=state,
            evidence_log=evidence_log,
        )
        self.evidence_log = evidence_log

    def execute(
        self,
        request: HFTOrderRequest,
        *,
        token: Any,
        feed_health: Optional[Dict[str, Any]] = None,
    ) -> HFTOrderResult:
        reason = self.gate.refusal_reason(request, self.gateway.state)
        if reason:
            return self.gateway.refuse_request(request, reason, token_status="canary_gate_refused")
        context = request.validation_context()
        context["sandbox"] = False
        return self.gateway.execute(
            request,
            token=token,
            feed_health=feed_health,
            validation_context_override=context,
        )

    def trigger_kill_switch(self, reason: str = "manual") -> None:
        self.gateway.trigger_kill_switch(reason)

    def rollback(self, reason: str = "manual_rollback") -> str:
        self.gateway.state.kill_switch_active = True
        return append_execution_evidence(
            event_type="hft_canary_rollback",
            execution_id=f"hft_canary_rollback_{int(time.time())}",
            operation="hft_execution",
            outcome="canceled",
            token_status="rollback",
            payload={"reason": reason},
            log_path=self.evidence_log,
        )
