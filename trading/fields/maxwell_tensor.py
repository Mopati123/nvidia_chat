"""Deterministic Maxwell-style field tensor for market geometry diagnostics."""

from __future__ import annotations

from typing import Dict, Iterable


def _last(values: Iterable[float], default: float = 0.0) -> float:
    seq = list(values or [])
    return float(seq[-1]) if seq else default


def compute_maxwell_tensor(market_state: Dict, geometry_data: Dict) -> Dict[str, float]:
    """Compute a compact field tensor from OHLCV, microstructure, and geometry."""
    ohlcv = market_state.get("ohlcv", {}) if isinstance(market_state, dict) else {}
    micro = market_state.get("microstructure", {}) if isinstance(market_state, dict) else {}
    close = [float(value) for value in ohlcv.get("close", []) if value is not None]
    high = [float(value) for value in ohlcv.get("high", []) if value is not None]
    low = [float(value) for value in ohlcv.get("low", []) if value is not None]

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
