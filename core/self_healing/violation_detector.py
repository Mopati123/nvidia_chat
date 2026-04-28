"""Violation detector scaffold backed by validator outputs."""

from typing import Any, List

META = {
    "tier": "rootfile",
    "layer": "core.self_healing",
    "operator_type": "violation_detector",
}


def detect_violations(*validator_results: Any) -> List[Any]:
    """Collect invalid validator results without repairing them."""
    return [result for result in validator_results if getattr(result, "valid", True) is False]

