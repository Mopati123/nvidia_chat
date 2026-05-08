"""Rootfile adapter for the canonical Apex engine."""

from trading.kernel.apex_engine import *  # noqa: F401,F403

from core.meta import OperatorMeta


META = OperatorMeta(
    tier="rootfile",
    layer="core.orchestration",
    operator_type="engine_adapter",
    canonical_law="H10",
)

