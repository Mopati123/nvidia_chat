"""Rootfile adapter for scheduler collapse authority."""

from trading.kernel.scheduler import *  # noqa: F401,F403
from trading.kernel.scheduler import Scheduler

from core.meta import OperatorMeta


META = OperatorMeta(
    tier="rootfile",
    layer="core.orchestration",
    operator_type="scheduler_adapter",
    canonical_law="H10",
)


def authorize_collapse(scheduler: Scheduler, **kwargs):
    """Explicit H10 lambda-law adapter over Scheduler.authorize_collapse."""
    return scheduler.authorize_collapse(**kwargs)

