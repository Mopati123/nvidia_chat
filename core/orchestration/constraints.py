"""Rootfile adapter for constraint Hamiltonian projectors."""

from trading.kernel.H_constraints import *  # noqa: F401,F403

from core.meta import OperatorMeta


META = OperatorMeta(
    tier="rootfile",
    layer="core.orchestration",
    operator_type="constraint_adapter",
    canonical_law="H8",
)

