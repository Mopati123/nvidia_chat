"""Canonical token validation used at execution boundaries."""

from __future__ import annotations

import time
import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Optional

META = {
    "tier": "rootfile",
    "layer": "core.authority",
    "operator_type": "validator",
}


@dataclass
class TokenValidationResult:
    """Result returned by the canonical token validator."""

    valid: bool
    reason: str = ""
    operation: Optional[str] = None


def validate_token(
    token: Any,
    operation: Optional[str] = None,
    allowed_operators: Optional[list[str]] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> TokenValidationResult:
    """Validate TAEP or trading-scheduler execution tokens."""
    if token is None:
        return TokenValidationResult(False, "missing execution token", operation)

    expired = getattr(token, "expired", None)
    if callable(expired) and expired():
        return TokenValidationResult(False, "expired execution token", operation)

    if hasattr(token, "expiry") and time.time() > getattr(token, "expiry"):
        return TokenValidationResult(False, "expired execution token", operation)

    if hasattr(token, "valid") and not getattr(token, "valid"):
        return TokenValidationResult(False, "revoked execution token", operation)

    verify = getattr(token, "verify", None)
    if callable(verify) and not verify():
        return TokenValidationResult(False, "invalid token signature", operation)

    token_operation = getattr(token, "operation", None)
    if operation and token_operation and not _operation_authorizes(token_operation, operation):
        return TokenValidationResult(
            False,
            f"token operation {token_operation!r} does not authorize {operation!r}",
            operation,
        )

    if operation == "hft_execution":
        scope_result = _validate_hft_scope(token, context or {})
        if not scope_result.valid:
            return scope_result
        if not _is_known_execution_token(token, operation):
            return TokenValidationResult(False, "unknown execution token authority", operation)
    elif not _is_known_execution_token(token, operation):
        return TokenValidationResult(False, "unknown execution token authority", operation)

    if allowed_operators is not None:
        token_allowed = getattr(token, "allowed_operators", None)
        if token_allowed is not None:
            missing = set(allowed_operators) - set(token_allowed)
            if missing:
                return TokenValidationResult(
                    False,
                    f"token missing allowed operators: {sorted(missing)}",
                    operation,
                )

    return TokenValidationResult(True, "authorized", operation)


def _operation_authorizes(token_operation: Any, requested: str) -> bool:
    return str(token_operation) in {requested, "*", "trade", "TRADE"}


def _is_known_execution_token(token: Any, operation: Optional[str]) -> bool:
    """Fail closed unless the token matches a known scheduler authority path."""
    if operation == "hft_execution":
        verify = getattr(token, "verify", None)
        return (
            hasattr(token, "scope")
            and getattr(token, "operation", None) == "hft_execution"
            and callable(verify)
            and bool(verify())
        )

    token_operation = getattr(token, "operation", None)
    if token_operation is not None:
        return _is_managed_taep_token(token, operation)

    if operation == "live_execution":
        return _is_scheduler_execution_token(token)

    return False


def _is_managed_taep_token(token: Any, operation: Optional[str]) -> bool:
    token_id = getattr(token, "token_id", None)
    if not token_id:
        return False

    token_operation = getattr(token, "operation", None)
    if operation and not _operation_authorizes(token_operation, operation):
        return False

    try:
        from core.authority.execution_token import _TOKEN_MANAGER
    except Exception:
        return False

    record = getattr(_TOKEN_MANAGER, "tokens", {}).get(str(token_id))
    if record is None or getattr(record, "revoked", False):
        return False
    if operation and not _operation_authorizes(getattr(record, "operation", None), operation):
        return False
    if float(getattr(record, "expires_at", 0.0) or 0.0) < time.time():
        return False

    expected = hashlib.sha256(
        f"{token_id}:{token_operation}:{getattr(token, 'expiry', None)}:{getattr(token, 'budget', None)}".encode()
    ).hexdigest()
    signature = getattr(token, "signature", None)
    return bool(signature and signature == expected)


def _is_scheduler_execution_token(token: Any) -> bool:
    required = (
        "token_id",
        "timestamp",
        "operator_weights",
        "trajectory_hash",
        "authorization_signature",
        "lambda_parameters",
        "authority_token_id",
    )
    if any(not hasattr(token, field) for field in required):
        return False
    if not getattr(token, "authority_token_id", None):
        return False
    verify = getattr(token, "verify", None)
    return callable(verify) and bool(verify())


def _scope_value(scope: Any, key: str, default: Any = None) -> Any:
    if isinstance(scope, Mapping):
        return scope.get(key, default)
    return getattr(scope, key, default)


def _validate_hft_scope(token: Any, context: Mapping[str, Any]) -> TokenValidationResult:
    scope = getattr(token, "scope", None)
    if scope is None:
        return TokenValidationResult(False, "missing hft execution scope", "hft_execution")

    token_operation = getattr(token, "operation", None)
    if token_operation != "hft_execution":
        return TokenValidationResult(
            False,
            f"token operation {token_operation!r} does not authorize 'hft_execution'",
            "hft_execution",
        )

    broker = str(context.get("broker", "")).lower()
    symbol = str(context.get("symbol", "")).upper()
    side = str(context.get("side", "")).lower()
    notional = float(context.get("notional", 0.0) or 0.0)
    slippage_bps = float(context.get("slippage_bps", 0.0) or 0.0)
    sandbox = bool(context.get("sandbox", True))

    if broker and broker != str(_scope_value(scope, "broker", "")).lower():
        return TokenValidationResult(False, "hft token broker scope mismatch", "hft_execution")
    if symbol and symbol != str(_scope_value(scope, "symbol", "")).upper():
        return TokenValidationResult(False, "hft token symbol scope mismatch", "hft_execution")
    if side and side != str(_scope_value(scope, "side", "")).lower():
        return TokenValidationResult(False, "hft token side scope mismatch", "hft_execution")

    max_notional = float(_scope_value(scope, "max_notional", 0.0) or 0.0)
    if notional > max_notional:
        return TokenValidationResult(False, "hft token notional limit exceeded", "hft_execution")

    max_slippage_bps = float(_scope_value(scope, "max_slippage_bps", 0.0) or 0.0)
    if slippage_bps > max_slippage_bps:
        return TokenValidationResult(False, "hft token slippage limit exceeded", "hft_execution")

    if bool(_scope_value(scope, "sandbox_only", True)) and not sandbox:
        return TokenValidationResult(False, "hft token is sandbox-only", "hft_execution")

    max_order_count = int(_scope_value(scope, "max_order_count", 0) or 0)
    if max_order_count <= 0:
        return TokenValidationResult(False, "hft token max_order_count must be positive", "hft_execution")

    return TokenValidationResult(True, "authorized", "hft_execution")

