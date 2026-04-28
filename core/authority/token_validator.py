"""Canonical token validation used at execution boundaries."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

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
    if operation and token_operation and token_operation not in {operation, "*", "trade", "TRADE"}:
        return TokenValidationResult(
            False,
            f"token operation {token_operation!r} does not authorize {operation!r}",
            operation,
        )

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

