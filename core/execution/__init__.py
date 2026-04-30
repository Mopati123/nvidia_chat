"""Canonical execution boundary adapters."""

from .hft import (
    FakeHFTBroker,
    HFTExecutionState,
    HFTOrderRequest,
    HFTOrderResult,
    HFTRiskLimits,
    HFTSandboxGateway,
)
from .hft_canary import (
    BinanceHFTExecutionAdapter,
    CanaryConfig,
    CanaryGate,
    CodeGatedHFTGateway,
    IBHFTExecutionAdapter,
    SandboxCertification,
    write_sandbox_certification,
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
    "BinanceHFTExecutionAdapter",
    "CanaryConfig",
    "CanaryGate",
    "CodeGatedHFTGateway",
    "IBHFTExecutionAdapter",
    "SandboxCertification",
    "execute_shadow_authorized",
    "write_sandbox_certification",
]

