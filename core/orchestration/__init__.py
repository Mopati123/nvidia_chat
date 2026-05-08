"""Canonical orchestration adapters for the existing trading kernel."""

from trading.kernel.H_constraints import ConstraintHamiltonian, ConstraintViolation, Projector
from trading.kernel.apex_engine import ApexEngine, ExecutionMode, ExecutionOutcome, ExecutionResult
from trading.kernel.scheduler import CollapseDecision, ExecutionToken, Scheduler

from core.meta import OperatorMeta


META = OperatorMeta(
    tier="rootfile",
    layer="core.orchestration",
    operator_type="orchestration_adapter",
    canonical_law="H10",
)

__all__ = [
    "ApexEngine",
    "CollapseDecision",
    "ConstraintHamiltonian",
    "ConstraintViolation",
    "ExecutionMode",
    "ExecutionOutcome",
    "ExecutionResult",
    "ExecutionToken",
    "Projector",
    "Scheduler",
]

