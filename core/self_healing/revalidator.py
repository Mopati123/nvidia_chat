"""Revalidation scaffold for post-repair checks."""

from typing import Any, Dict

META = {
    "tier": "rootfile",
    "layer": "core.self_healing",
    "operator_type": "revalidator",
}


def revalidate(*results: Any) -> Dict[str, Any]:
    """Summarize validator results."""
    failed = [result for result in results if getattr(result, "valid", True) is False]
    return {"valid": not failed, "failed": failed}

