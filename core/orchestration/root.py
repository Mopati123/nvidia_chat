"""H-root runtime setup helpers for lawful-collapse state."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from core.meta import OperatorMeta


META = OperatorMeta(
    tier="rootfile",
    layer="core.orchestration",
    operator_type="root_runtime_setup",
    canonical_law="H1",
)


DEFAULT_RUNTIME_DIRS = (
    "logs",
    "data/models",
    "trading_data/pnl",
)


def setup_runtime(root: str | Path = ".", dirs: Iterable[str] = DEFAULT_RUNTIME_DIRS) -> list[Path]:
    """Create required runtime directories and return the created/resolved paths."""
    base = Path(root)
    paths = []
    for rel in dirs:
        path = base / rel
        path.mkdir(parents=True, exist_ok=True)
        paths.append(path)
    return paths
