"""Canonical execution boundary adapters."""

from .shadow import execute_shadow_authorized

META = {
    "tier": "rootfile",
    "layer": "core.execution",
    "operator_type": "execution_boundary",
}

__all__ = ["execute_shadow_authorized"]

