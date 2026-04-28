"""Read-only repository perception for future repair planning."""

from pathlib import Path
from typing import Dict, List

META = {
    "tier": "rootfile",
    "layer": "core.self_healing",
    "operator_type": "perception",
}


def perceive(root: str | Path) -> Dict[str, List[str]]:
    """Return a small read-only inventory of Python files."""
    base = Path(root)
    return {"python_files": [str(p.relative_to(base)) for p in base.rglob("*.py")]}

