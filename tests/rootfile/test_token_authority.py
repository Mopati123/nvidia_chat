import pytest

from trading.kernel import CollapseDecision, Scheduler, TokenAuthority
from trading.kernel.apex_engine import ApexEngine, ExecutionOutcome
from trading.pipeline.orchestrator import PipelineOrchestrator, PipelineStage


def _trajectory(trajectory_id="traj_a"):
    return {
        "id": trajectory_id,
        "energy": 0.1,
        "action": 0.0,
        "operator_scores": {"kinetic": 1.0},
        "predicted_pnl": 0.0,
    }


def test_token_authority_limits_concurrency_and_releases_on_exception():
    authority = TokenAuthority(max_active_tokens=1, default_budget=5.0)

    first = authority.issue_token("operator_a")
    assert first is not None
    assert first.budget == 5.0
    assert authority.issue_token("operator_b") is None

    authority.release_token(first)
    assert authority.active_count == 0

    with pytest.raises(RuntimeError):
        with authority.acquire_token("operator_c") as leased:
            assert leased is not None
            assert authority.active_count == 1
            raise RuntimeError("simulated collapse failure")

    assert authority.active_count == 0


def test_scheduler_refuses_when_authority_capacity_is_exhausted_then_recovers():
    authority = TokenAuthority(max_active_tokens=1, default_budget=1.0)
    scheduler = Scheduler(config={"use_rl": False}, token_authority=authority)
    proposal = {"symbol": "EURUSD", "size": 0.5}
    trajectories = [_trajectory()]

    decision, first_token = scheduler.authorize_collapse(
        proposal=proposal,
        projected_trajectories=trajectories,
        delta_s=0.1,
        constraints_passed=True,
        reconciliation_clear=True,
    )

    assert decision == CollapseDecision.AUTHORIZED
    assert first_token is not None
    assert first_token.authority_token_id is not None
    assert first_token.authority_owner == "scheduler_collapse:EURUSD:traj_a"
    assert authority.active_count == 1

    refused, refused_token = scheduler.authorize_collapse(
        proposal=proposal,
        projected_trajectories=trajectories,
        delta_s=0.1,
        constraints_passed=True,
        reconciliation_clear=True,
    )

    assert refused == CollapseDecision.REFUSED
    assert refused_token is None

    scheduler.release_execution_token(first_token)
    assert authority.active_count == 0

    recovered, recovered_token = scheduler.authorize_collapse(
        proposal=proposal,
        projected_trajectories=trajectories,
        delta_s=0.1,
        constraints_passed=True,
        reconciliation_clear=True,
    )

    assert recovered == CollapseDecision.AUTHORIZED
    assert recovered_token is not None
    scheduler.release_execution_token(recovered_token)


class _PassingConstraints:
    def evaluate_projectors(self, trajectories, market_state):
        return {
            "admissible_trajectories": trajectories,
            "all_passed": True,
            "risk": True,
            "session": True,
        }

    def get_admissibility_status(self):
        return {"ok": True}


def test_apex_engine_releases_scheduler_authority_after_successful_cycle():
    authority = TokenAuthority(max_active_tokens=1, default_budget=1.0)
    scheduler = Scheduler(config={"use_rl": False}, token_authority=authority)
    engine = ApexEngine(scheduler=scheduler, constraints=_PassingConstraints())

    result = engine.execute_canonical_cycle(
        proposal={"symbol": "EURUSD", "size": 0.1},
        market_state={},
        path_integral_result={"trajectories": [_trajectory()]},
    )

    assert result.outcome == ExecutionOutcome.SUCCESS
    assert result.token is not None
    assert authority.active_count == 0


def test_pipeline_orchestrator_releases_scheduler_authority_after_success():
    authority = TokenAuthority(max_active_tokens=1, default_budget=1.0)
    scheduler = Scheduler(config={"use_rl": False}, token_authority=authority)
    orchestrator = PipelineOrchestrator(scheduler=scheduler, use_microstructure=False)

    def no_op_stage(context):
        return {}

    def collapse_stage(context):
        decision, token = scheduler.authorize_collapse(
            proposal={"symbol": context.symbol, "size": 0.1},
            projected_trajectories=[_trajectory()],
            delta_s=0.1,
            constraints_passed=True,
            reconciliation_clear=True,
        )
        context.collapse_decision = decision.name
        context.execution_token = token
        return {"decision": decision.name, "token": token.token_id if token else None}

    orchestrator.stage_handlers = {
        stage: no_op_stage
        for stage in orchestrator.stage_handlers
    }
    orchestrator.stage_handlers[PipelineStage.SCHEDULER_COLLAPSE] = collapse_stage

    context = orchestrator.execute(raw_data={}, symbol="EURUSD")

    assert context.collapse_decision == CollapseDecision.AUTHORIZED.name
    assert context.execution_token is not None
    assert authority.active_count == 0
