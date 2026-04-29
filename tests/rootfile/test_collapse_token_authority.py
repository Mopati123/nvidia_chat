"""Collapse token-authority tests for scheduler-owned execution control."""

import pytest

from trading.kernel.apex_engine import ApexEngine, ExecutionMode, ExecutionOutcome
from trading.kernel.scheduler import CollapseDecision, Scheduler
from trading.kernel.token_authority import TokenAuthority


def _trajectory(action: float = 0.1) -> dict:
    return {
        "id": "collapse_path",
        "energy": 0.2,
        "action": action,
        "action_score": 0.8,
        "operator_scores": {"kinetic": 0.9},
        "kinetic": 0.9,
        "position_size": 0.01,
        "risk_percent": 0.5,
        "sailing_lane_leg": 0,
        "allowed_sessions": ["london"],
        "predicted_pnl": 0.01,
    }


def _market_state() -> dict:
    return {
        "session": "london",
        "regime": "neutral",
        "max_position_size": 1.0,
        "max_risk_percent": 2.0,
        "max_sailing_lane_legs": 5,
        "reconciliation_threshold": 0.05,
    }


def _authorize(scheduler: Scheduler, trajectory: dict | None = None):
    return scheduler.authorize_collapse(
        proposal={"symbol": "EURUSD"},
        projected_trajectories=[trajectory or _trajectory()],
        delta_s=0.0,
        constraints_passed=True,
        reconciliation_clear=True,
    )


def test_token_authority_acquire_consume_release_and_release_all():
    authority = TokenAuthority(max_active_tokens=2, default_budget=1.0, total_budget=1.5)

    first = authority.acquire_lease(0.5)
    second = authority.acquire_lease(0.75)

    assert first is not None
    assert second is not None
    assert authority.active_count == 2
    assert authority.acquire_lease(0.1) is None
    assert first.consume(0.2)
    assert not first.consume(0.4)

    assert authority.release_lease(first)
    assert first.released is True
    assert authority.active_count == 1

    assert authority.release_all() == 1
    assert authority.active_count == 0
    assert authority.budget_available == pytest.approx(1.5)


def test_scheduler_refuses_when_authority_capacity_is_exhausted():
    authority = TokenAuthority(max_active_tokens=1, default_budget=1.0, total_budget=1.0)
    scheduler = Scheduler(config={"use_rl": False}, token_authority=authority)

    first_decision, first_token = _authorize(scheduler)
    second_decision, second_token = _authorize(scheduler)

    assert first_decision == CollapseDecision.AUTHORIZED
    assert first_token is not None
    assert first_token.authority_token_id
    assert first_token.budget_allocated == pytest.approx(0.1)
    assert second_decision == CollapseDecision.REFUSED
    assert second_token is None

    assert scheduler.release_execution_token(first_token)
    assert authority.active_count == 0


def test_scheduler_refuses_when_requested_budget_exceeds_authority_limit():
    authority = TokenAuthority(max_active_tokens=1, default_budget=0.05, total_budget=0.05)
    scheduler = Scheduler(
        config={"use_rl": False, "collapse_budget": 0.05},
        token_authority=authority,
    )

    decision, token = _authorize(scheduler, _trajectory(action=0.1))

    assert decision == CollapseDecision.REFUSED
    assert token is None
    assert authority.active_count == 0


def test_scheduler_epoch_end_releases_outstanding_authority_leases():
    authority = TokenAuthority(max_active_tokens=2, default_budget=1.0, total_budget=1.0)
    scheduler = Scheduler(config={"use_rl": False}, token_authority=authority)

    decision, token = _authorize(scheduler)

    assert decision == CollapseDecision.AUTHORIZED
    assert token is not None
    assert authority.active_count == 1

    scheduler.epoch_end()

    assert authority.active_count == 0
    assert authority.budget_available == pytest.approx(1.0)
    assert not scheduler.release_execution_token(token)


def test_apex_engine_releases_authority_lease_after_successful_cycle():
    authority = TokenAuthority(max_active_tokens=1, default_budget=1.0, total_budget=1.0)
    scheduler = Scheduler(config={"use_rl": False}, token_authority=authority)
    engine = ApexEngine(scheduler=scheduler)

    result = engine.execute_canonical_cycle(
        proposal={"symbol": "EURUSD"},
        market_state=_market_state(),
        path_integral_result={"trajectories": [_trajectory()]},
        mode=ExecutionMode.SHADOW,
    )

    assert result.outcome in {ExecutionOutcome.SUCCESS, ExecutionOutcome.ERROR}
    assert result.token is not None
    assert result.token.authority_token_id
    assert authority.active_count == 0


def test_apex_engine_releases_authority_lease_when_execution_raises(monkeypatch):
    authority = TokenAuthority(max_active_tokens=1, default_budget=1.0, total_budget=1.0)
    scheduler = Scheduler(config={"use_rl": False}, token_authority=authority)
    engine = ApexEngine(scheduler=scheduler)

    def fail_shadow(*args, **kwargs):
        raise RuntimeError("shadow execution failed")

    monkeypatch.setattr(engine, "_execute_shadow", fail_shadow)

    with pytest.raises(RuntimeError, match="shadow execution failed"):
        engine.execute_canonical_cycle(
            proposal={"symbol": "EURUSD"},
            market_state=_market_state(),
            path_integral_result={"trajectories": [_trajectory()]},
            mode=ExecutionMode.SHADOW,
        )

    assert authority.active_count == 0

