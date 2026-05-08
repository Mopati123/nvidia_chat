"""Operator metadata helpers for rootfile law introspection."""

from __future__ import annotations

from typing import Any, Callable, Mapping, NamedTuple, TypeVar


class OperatorMeta(NamedTuple):
    """Canonical operator metadata attached to modules, classes, or functions."""

    tier: str
    layer: str
    operator_type: str
    canonical_law: str = ""


T = TypeVar("T")


def normalize_meta(meta: OperatorMeta | Mapping[str, Any]) -> OperatorMeta:
    """Convert legacy dict metadata or OperatorMeta into OperatorMeta."""
    if isinstance(meta, OperatorMeta):
        return meta
    return OperatorMeta(
        tier=str(meta.get("tier", "")),
        layer=str(meta.get("layer", "")),
        operator_type=str(meta.get("operator_type", "")),
        canonical_law=str(meta.get("canonical_law", "")),
    )


def declare_operator(meta: OperatorMeta | Mapping[str, Any]) -> Callable[[T], T]:
    """Attach canonical rootfile metadata to a function or class."""
    normalized = normalize_meta(meta)

    def decorator(obj: T) -> T:
        setattr(obj, "__operator_meta__", normalized)
        return obj

    return decorator


def get_declared_meta(obj: Any) -> OperatorMeta | None:
    """Return metadata declared with @declare_operator, if present."""
    meta = getattr(obj, "__operator_meta__", None)
    if meta is None:
        return None
    return normalize_meta(meta)
