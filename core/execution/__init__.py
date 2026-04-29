"""Canonical execution boundary adapters."""

from .hft import (
    FakeHFTBroker,
    HFTExecutionState,
    HFTOrderRequest,
    HFTOrderResult,
    HFTRiskLimits,
    HFTSandboxGateway,
)
from .shadow import execute_shadow_authorized

META = {
    "tier": "rootfile",
    "layer": "core.execution",
    "operator_type": "execution_boundary",
}

__all__ = [
    "FakeHFTBroker",
    "HFTExecutionState",
    "HFTOrderRequest",
    "HFTOrderResult",
    "HFTRiskLimits",
    "HFTSandboxGateway",
    "execute_shadow_authorized",
]

