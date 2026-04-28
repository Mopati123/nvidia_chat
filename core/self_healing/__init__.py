"""Inert self-healing scaffold for future validator-guided repair."""

from .perception import perceive
from .repair_executor import execute_repair_plan
from .repair_planner import plan_repair
from .revalidator import revalidate
from .violation_detector import detect_violations

META = {
    "tier": "rootfile",
    "layer": "core.self_healing",
    "operator_type": "repair_scaffold",
}

__all__ = [
    "detect_violations",
    "execute_repair_plan",
    "perceive",
    "plan_repair",
    "revalidate",
]

