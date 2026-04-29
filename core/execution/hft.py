"""Sandbox-only HFT execution boundary.

This module is intentionally broker-fake first. Real adapters must live behind
additional environment gates and are not implemented here.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from core.authority.token_validator import validate_token
from tachyonic_chain.audit_log import append_execution_evidence

META = {
    "tier": "rootfile",
    "layer": "core.execution",
    "operator_type": "hft_sandbox_execution",
}


@dataclass(frozen=True)
class HFTOrderRequest:
    """A single sandbox HFT order attempt."""

    broker: str
    symbol: str
    side: str
    quantity: float
    price: float
    max_slippage_bps: float
    strategy_id: str
    idempotency_key: str
    timestamp: float = field(default_factory=time.time)
    sandbox: bool = True

    @property
    def notional(self) -> float:
        return abs(float(self.quantity) * float(self.price))

    def validation_context(self) -> Dict[str, Any]:
        return {
            "broker": self.broker,
            "symbol": self.symbol,
            "side": self.side,
            "notional": self.notional,
            "slippage_bps": self.max_slippage_bps,
            "sandbox": self.sandbox,
        }


@dataclass
class HFTOrderResult:
    """Structured result from the sandbox HFT gateway."""

    accepted: bool
    outcome: str
    reason: str
    broker: str
    symbol: str
    side: str
    quantity: float
    price: float
    notional: float
    idempotency_key: str
    order_id: Optional[str] = None
    evidence_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HFTRiskLimits:
    """Hard limits for sandbox HFT execution attempts."""

    max_orders_per_minute: int = 5
    max_open_notional: float = 100.0
    daily_loss_cap: float = 25.0
    per_symbol_exposure: float = 50.0
    stale_feed_cutoff_seconds: float = 2.0
    max_slippage_bps: float = 5.0
    retry_cap: int = 0
    cooldown_after_failures_seconds: float = 30.0
    max_failures_before_cooldown: int = 3


@dataclass
class HFTExecutionState:
    """In-memory sandbox execution state."""

    open_notional: float = 0.0
    daily_pnl: float = 0.0
    per_symbol_notional: Dict[str, float] = field(default_factory=dict)
    order_timestamps: list[float] = field(default_factory=list)
    token_order_counts: Dict[str, int] = field(default_factory=dict)
    failure_count: int = 0
    cooldown_until: float = 0.0
    kill_switch_active: bool = False


class FakeHFTBroker:
    """No-network fake broker used for sandbox and CI execution tests."""

    def __init__(self, *, fail_next: bool = False) -> None:
        self.fail_next = fail_next
        self.orders: list[HFTOrderRequest] = []

    def place_order(self, request: HFTOrderRequest) -> Dict[str, Any]:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("fake broker failure")
        self.orders.append(request)
        return {
            "order_id": f"fake_{len(self.orders)}_{int(time.time() * 1000)}",
            "status": "accepted",
        }


class HFTSandboxGateway:
    """Token-gated, risk-limited sandbox HFT execution gateway."""

    def __init__(
        self,
        *,
        broker: Optional[FakeHFTBroker] = None,
        limits: Optional[HFTRiskLimits] = None,
        state: Optional[HFTExecutionState] = None,
        evidence_log: Optional[str] = None,
    ) -> None:
        self.broker = broker or FakeHFTBroker()
        self.limits = limits or HFTRiskLimits()
        self.state = state or HFTExecutionState()
        self.evidence_log = evidence_log
        self._idempotency_results: Dict[str, HFTOrderResult] = {}

    def execute(
        self,
        request: HFTOrderRequest,
        *,
        token: Any,
        feed_health: Optional[Dict[str, Any]] = None,
        validation_context_override: Optional[Dict[str, Any]] = None,
    ) -> HFTOrderResult:
        """Validate token/risk gates and submit to the fake sandbox broker."""
        duplicate = self._idempotency_results.get(request.idempotency_key)
        if duplicate is not None:
            return self._refuse(request, "duplicate_idempotency_key", token_status="not_submitted")

        validation = validate_token(
            token,
            operation="hft_execution",
            context=validation_context_override or request.validation_context(),
        )
        if not validation.valid:
            return self._refuse(request, validation.reason, token_status=validation.reason)

        risk_refusal = self._risk_refusal_reason(request, token=token, feed_health=feed_health)
        if risk_refusal:
            return self._refuse(request, risk_refusal, token_status="authorized")

        try:
            broker_result = self.broker.place_order(request)
        except Exception as exc:  # noqa: BLE001 - convert broker failure into evidence
            self._record_failure()
            return self._failed(request, str(exc))

        result = HFTOrderResult(
            accepted=True,
            outcome="accepted",
            reason="sandbox_order_accepted",
            broker=request.broker,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            notional=request.notional,
            idempotency_key=request.idempotency_key,
            order_id=str(broker_result.get("order_id")),
        )
        self._register_acceptance(request, token)
        self._emit(result, event_type="hft_execution", token_status="authorized")
        self._idempotency_results[request.idempotency_key] = result
        return result

    def cancel_order(self, request: HFTOrderRequest, *, token: Any, order_id: str) -> HFTOrderResult:
        validation = validate_token(token, operation="hft_execution", context=request.validation_context())
        if not validation.valid:
            return self._refuse(request, validation.reason, token_status=validation.reason)
        result = HFTOrderResult(
            accepted=True,
            outcome="canceled",
            reason="sandbox_cancel_recorded",
            broker=request.broker,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            notional=request.notional,
            idempotency_key=request.idempotency_key,
            order_id=order_id,
        )
        self._emit(result, event_type="hft_cancel", token_status="authorized")
        return result

    def reconcile_order(
        self,
        request: HFTOrderRequest,
        *,
        order_id: str,
        realized_pnl: float,
    ) -> HFTOrderResult:
        self.state.daily_pnl += realized_pnl
        self.state.open_notional = max(0.0, self.state.open_notional - request.notional)
        self.state.per_symbol_notional[request.symbol] = max(
            0.0,
            self.state.per_symbol_notional.get(request.symbol, 0.0) - request.notional,
        )
        result = HFTOrderResult(
            accepted=True,
            outcome="reconciled",
            reason="sandbox_reconciliation_recorded",
            broker=request.broker,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            notional=request.notional,
            idempotency_key=request.idempotency_key,
            order_id=order_id,
        )
        self._emit(
            result,
            event_type="hft_reconcile",
            token_status="authorized",
            extra_payload={"realized_pnl": realized_pnl},
        )
        return result

    def trigger_kill_switch(self, reason: str = "manual") -> None:
        self.state.kill_switch_active = True
        append_execution_evidence(
            event_type="hft_kill_switch",
            execution_id=f"hft_kill_{int(time.time())}",
            operation="hft_execution",
            outcome="canceled",
            token_status="kill_switch",
            payload={"reason": reason},
            log_path=self.evidence_log,
        )

    def refuse_request(
        self,
        request: HFTOrderRequest,
        reason: str,
        *,
        token_status: str = "not_submitted",
    ) -> HFTOrderResult:
        """Public refusal helper for higher-level gated execution wrappers."""
        return self._refuse(request, reason, token_status=token_status)

    def _risk_refusal_reason(
        self,
        request: HFTOrderRequest,
        *,
        token: Any,
        feed_health: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        now = time.time()
        if self.state.kill_switch_active:
            return "kill_switch_active"
        if now < self.state.cooldown_until:
            return "cooldown_active"
        if request.max_slippage_bps > self.limits.max_slippage_bps:
            return "slippage_limit_exceeded"
        if self.state.daily_pnl <= -abs(self.limits.daily_loss_cap):
            return "daily_loss_cap_exceeded"
        if feed_health:
            age = feed_health.get("update_age_seconds")
            if feed_health.get("stale") or (age is not None and age > self.limits.stale_feed_cutoff_seconds):
                return "stale_feed"

        one_minute_ago = now - 60.0
        self.state.order_timestamps = [ts for ts in self.state.order_timestamps if ts >= one_minute_ago]
        if len(self.state.order_timestamps) >= self.limits.max_orders_per_minute:
            return "orders_per_minute_limit_exceeded"

        if self.state.open_notional + request.notional > self.limits.max_open_notional:
            return "open_notional_limit_exceeded"
        symbol_notional = self.state.per_symbol_notional.get(request.symbol, 0.0)
        if symbol_notional + request.notional > self.limits.per_symbol_exposure:
            return "per_symbol_exposure_limit_exceeded"

        token_id = str(getattr(token, "token_id", "unknown"))
        max_order_count = int(getattr(getattr(token, "scope", None), "max_order_count", 0) or 0)
        if self.state.token_order_counts.get(token_id, 0) >= max_order_count:
            return "token_order_count_exceeded"

        return None

    def _register_acceptance(self, request: HFTOrderRequest, token: Any) -> None:
        self.state.order_timestamps.append(time.time())
        self.state.open_notional += request.notional
        self.state.per_symbol_notional[request.symbol] = (
            self.state.per_symbol_notional.get(request.symbol, 0.0) + request.notional
        )
        token_id = str(getattr(token, "token_id", "unknown"))
        self.state.token_order_counts[token_id] = self.state.token_order_counts.get(token_id, 0) + 1

    def _record_failure(self) -> None:
        self.state.failure_count += 1
        if self.state.failure_count >= self.limits.max_failures_before_cooldown:
            self.state.cooldown_until = time.time() + self.limits.cooldown_after_failures_seconds

    def _refuse(self, request: HFTOrderRequest, reason: str, *, token_status: str) -> HFTOrderResult:
        result = HFTOrderResult(
            accepted=False,
            outcome="refused",
            reason=reason,
            broker=request.broker,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            notional=request.notional,
            idempotency_key=request.idempotency_key,
        )
        self._emit(result, event_type="hft_refusal", token_status=token_status)
        return result

    def _failed(self, request: HFTOrderRequest, reason: str) -> HFTOrderResult:
        result = HFTOrderResult(
            accepted=False,
            outcome="failed",
            reason=reason,
            broker=request.broker,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            notional=request.notional,
            idempotency_key=request.idempotency_key,
        )
        self._emit(result, event_type="hft_execution", token_status="authorized")
        return result

    def _emit(
        self,
        result: HFTOrderResult,
        *,
        event_type: str,
        token_status: str,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = result.to_dict()
        if extra_payload:
            payload.update(extra_payload)
        result.evidence_hash = append_execution_evidence(
            event_type=event_type,
            execution_id=result.order_id or f"hft_{result.outcome}_{int(time.time() * 1000)}",
            operation="hft_execution",
            symbol=result.symbol,
            outcome=result.outcome,
            token_status=token_status,
            payload=payload,
            log_path=self.evidence_log,
        )
