"""Execution-token authority facade over existing TAEP and trading tokens."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .hft_token import HFTExecutionScope
from taep.scheduler.execution_token import ExecutionTokenManager

META = {
    "tier": "rootfile",
    "layer": "core.authority",
    "operator_type": "authority_facade",
}

AuthorityToken = Any


_TOKEN_MANAGER = ExecutionTokenManager()


def issue_execution_token(
    operation: str,
    budget: float,
    expiry_duration: float = 300.0,
    constraints: Optional[Dict[str, Any]] = None,
) -> AuthorityToken:
    """Issue a TAEP execution token through the canonical authority facade."""
    return _TOKEN_MANAGER.issue_token(
        operation=operation,
        budget=budget,
        expiry_duration=expiry_duration,
        constraints=constraints,
    )


def issue_trading_token(scheduler: Any, trajectory: Optional[Dict[str, Any]] = None) -> AuthorityToken:
    """Ask the trading scheduler to mint its native token for a selected trajectory."""
    if trajectory is None:
        trajectory = {
            "id": "rootfile_authorized",
            "energy": 0.0,
            "action": 0.0,
            "action_score": 0.0,
        }
    issue = getattr(scheduler, "_issue_token", None)
    if issue is None:
        raise TypeError("scheduler does not expose a token issuance method")
    return issue(trajectory)


def issue_hft_execution_token(scheduler: Any, scope: HFTExecutionScope) -> AuthorityToken:
    """Ask the scheduler to mint scoped HFT execution authority."""
    issue = getattr(scheduler, "issue_hft_execution_token", None)
    if issue is None:
        raise TypeError("scheduler does not expose HFT token issuance")
    return issue(scope)

