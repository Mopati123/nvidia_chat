"""Token-gated shadow execution boundary."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from trading.shadow.shadow_trading_loop import ShadowExecution, ShadowTradingLoop

META = {
    "tier": "rootfile",
    "layer": "core.execution",
    "operator_type": "shadow_execution_adapter",
}


def execute_shadow_authorized(
    symbol: str,
    ohlcv_data: List[Dict],
    bias: str = "neutral",
    session: str = "neutral",
    *,
    token: Any,
    loop: Optional[ShadowTradingLoop] = None,
) -> ShadowExecution:
    """Run shadow execution only after token validation."""
    trading_loop = loop or ShadowTradingLoop()
    return trading_loop.execute_shadow(
        symbol=symbol,
        ohlcv_data=ohlcv_data,
        bias=bias,
        session=session,
        token=token,
        require_token=True,
    )

