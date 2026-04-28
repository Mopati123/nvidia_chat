"""Rootfile enforcement adapters for Telegram trading entrypoints."""

from __future__ import annotations

import time
from typing import Any, Optional, Tuple


def install_telegram_authorization() -> None:
    """Attach scheduler authorization to Telegram manual trades."""
    try:
        from . import trading_live
        from tachyonic_chain.audit_log import append_execution_evidence
        from trading.kernel.scheduler import CollapseDecision, Scheduler
    except Exception:
        return

    if getattr(trading_live, "_ROOTFILE_ENFORCEMENT_INSTALLED", False):
        return

    def _ensure_scheduler(system: Any) -> Scheduler:
        scheduler = getattr(system, "scheduler", None)
        if scheduler is None:
            scheduler = Scheduler()
            system.scheduler = scheduler
        return scheduler

    def authorize_manual_trade(
        self: Any,
        symbol: str,
        direction: str,
        volume: float,
    ) -> Tuple[Optional[Any], str]:
        scheduler = _ensure_scheduler(self)
        proposal = {
            "symbol": symbol,
            "direction": direction,
            "volume": volume,
            "source": "telegram_manual",
            "mode": getattr(self, "mode", "shadow"),
        }
        projected = [{
            "id": f"telegram_manual_{symbol}_{int(time.time())}",
            "energy": 0.0,
            "action": 0.0,
            "action_score": 0.0,
            "operator_scores": {"risk": 1.0},
        }]
        decision, token = scheduler.authorize_collapse(
            proposal=proposal,
            projected_trajectories=projected,
            delta_s=0.0,
            constraints_passed=True,
            reconciliation_clear=True,
        )
        if decision != CollapseDecision.AUTHORIZED or token is None:
            reason = f"scheduler_{decision.value}"
            append_execution_evidence(
                event_type="live_refusal",
                execution_id=f"telegram_refused_{symbol}_{int(time.time())}",
                operation="live_execution",
                symbol=symbol,
                outcome="refused",
                token_status=reason,
                payload=proposal,
            )
            return None, reason
        return token, "authorized"

    trading_live.LiveTradingSystem.authorize_manual_trade = authorize_manual_trade
    _ensure_scheduler(trading_live.live_trading)

    original_trade_command = trading_live.trade_command

    async def trade_command_with_authorization(update: Any, context: Any) -> None:
        args = getattr(context, "args", [])
        if len(args) < 2:
            await original_trade_command(update, context)
            return

        symbol = args[0].upper()
        direction = args[1].lower()
        volume = float(args[2]) if len(args) > 2 else 0.01
        token, reason = trading_live.live_trading.authorize_manual_trade(
            symbol, direction, volume
        )
        if token is None:
            await update.message.reply_text(f"Trade authorization refused: {reason}")
            return

        original_execute = trading_live.live_trading.execute_trade

        def execute_with_token(
            trade_symbol: str,
            trade_direction: str,
            trade_volume: float = 0.01,
            sl: Optional[float] = None,
            tp: Optional[float] = None,
            token: Optional[Any] = token,
        ) -> Any:
            return original_execute(
                trade_symbol,
                trade_direction,
                trade_volume,
                sl,
                tp,
                token=token,
            )

        trading_live.live_trading.execute_trade = execute_with_token
        try:
            await original_trade_command(update, context)
        finally:
            trading_live.live_trading.execute_trade = original_execute

    trading_live.trade_command = trade_command_with_authorization
    trading_live._ROOTFILE_ENFORCEMENT_INSTALLED = True
