"""Deterministic Maxwell-style field tensor for market geometry diagnostics."""

from __future__ import annotations

from typing import Any, Dict, Iterable


def _last(values: Iterable[float], default: float = 0.0) -> float:
    seq = list(values or [])
    return float(seq[-1]) if seq else default


def _series(ohlcv: Any, key: str) -> list[float]:
    if isinstance(ohlcv, dict):
        values = ohlcv.get(key, [])
    elif isinstance(ohlcv, list):
        values = [
            item.get(key)
            for item in ohlcv
            if isinstance(item, dict)
        ]
    else:
        values = []
    return [float(value) for value in values if value is not None]


def compute_maxwell_tensor(market_state: Dict, geometry_data: Dict) -> Dict[str, float]:
    """Compute a compact field tensor from OHLCV, microstructure, and geometry."""
    ohlcv = market_state.get("ohlcv", {}) if isinstance(market_state, dict) else {}
    micro = market_state.get("microstructure", {}) if isinstance(market_state, dict) else {}
    close = _series(ohlcv, "close")
    high = _series(ohlcv, "high")
    low = _series(ohlcv, "low")

    latest_close = _last(close, float(micro.get("mid", 0.0) or 0.0))
    prev_close = close[-2] if len(close) >= 2 else latest_close
    impulse = latest_close - prev_close
    spread_proxy = abs(_last(high, latest_close) - _last(low, latest_close))
    phi = float(geometry_data.get("phi", 0.0) or 0.0)
    curvature = geometry_data.get("curvature", {}) or {}
    curvature_k = float(curvature.get("gaussian_curvature", curvature.get("K", 0.0)) or 0.0)

    electric_impulse = impulse + 0.1 * phi
    magnetic_liquidity = spread_proxy + abs(curvature_k)
    field_energy = electric_impulse * electric_impulse + magnetic_liquidity * magnetic_liquidity
    return {
        "F_qt": electric_impulse,
        "F_tq": -electric_impulse,
        "electric_impulse": electric_impulse,
        "magnetic_liquidity": magnetic_liquidity,
        "field_energy": field_energy,
    }
