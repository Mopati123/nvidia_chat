"""H-meta registry for rootfile operator jurisdiction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable

from core.meta import OperatorMeta, normalize_meta
from core.rootfile_manifest import LAWS


META = OperatorMeta(
    tier="rootfile",
    layer="core.orchestration",
    operator_type="operator_registry",
    canonical_law="H10",
)


@dataclass
class OperatorRegistry:
    """In-memory registry of operator metadata keyed by stable name."""

    operators: Dict[str, OperatorMeta] = field(default_factory=dict)

    def register(self, name: str, meta: OperatorMeta | dict) -> OperatorMeta:
        normalized = normalize_meta(meta)
        if normalized.canonical_law and normalized.canonical_law not in LAWS:
            raise ValueError(f"{name} declares unknown canonical law {normalized.canonical_law}")
        self.operators[name] = normalized
        return normalized

    def register_many(self, items: Iterable[tuple[str, OperatorMeta | dict]]) -> None:
        for name, meta in items:
            self.register(name, meta)

    def assert_jurisdiction(self, name: str, law_id: str) -> None:
        meta = self.operators.get(name)
        if meta is None:
            raise KeyError(f"operator not registered: {name}")
        if meta.canonical_law and meta.canonical_law != law_id:
            raise PermissionError(f"{name} belongs to {meta.canonical_law}, not {law_id}")
