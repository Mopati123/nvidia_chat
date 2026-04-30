"""Canonical execution authority facade."""

from .execution_token import AuthorityToken, issue_execution_token, issue_trading_token
from .token_validator import TokenValidationResult, validate_token

META = {
    "tier": "rootfile",
    "layer": "core.authority",
    "operator_type": "authority",
}

__all__ = [
    "AuthorityToken",
    "TokenValidationResult",
    "issue_execution_token",
    "issue_trading_token",
    "validate_token",
]

