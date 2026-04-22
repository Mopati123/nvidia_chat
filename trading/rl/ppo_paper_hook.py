"""
PPO Paper Trading Hook (T2-C)

Attaches PPO training to PaperTradingLoop via its handler hooks.
Records (state, action, log_prob, value) at trade entry, then completes
the transition with the realized PnL reward when the trade closes.
Triggers agent.update() whenever the rollout buffer reaches capacity.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional, Tuple

import numpy as np

if TYPE_CHECKING:
    from trading.paper_trading_loop import PaperTradeContext
    from trading.rl.scheduler_agent import PPOSchedulerAgent

logger = logging.getLogger(__name__)


class PPOPaperHook:
    """
    Connects PPO training loop to the paper trading loop.

    Usage:
        hook = PPOPaperHook(agent)
        loop = PaperTradingLoop(ppo_hook=hook)
        loop.start()
    """

    STATE_DIM = 166  # 128 embedding + 5 energies + 5 actions + 18 ops + 10 pnl

    def __init__(self, agent: "PPOSchedulerAgent") -> None:
        self.agent = agent
        # trade_id -> (state_vec, action_idx, log_prob, value)
        self._pending: Dict[str, Tuple[np.ndarray, int, float, float]] = {}

    # ------------------------------------------------------------------
    # Hooks called by PaperTradingLoop
    # ------------------------------------------------------------------

    def on_trade_executed(self, context: "PaperTradeContext") -> None:
        """Called as post_trade_handler right after trade entry."""
        if context.status != "executed":
            return
        state_vec = self._build_state(context)
        try:
            action_idx, log_prob, value = self.agent.select_action(state_vec)
        except Exception as exc:
            logger.warning("PPO select_action failed: %s", exc)
            return
        trade_id = self._trade_id(context)
        self._pending[trade_id] = (state_vec, int(action_idx), float(log_prob), float(value))

    def on_trade_closed(self, trade_id: str, pnl: float) -> None:
        """Called after close_position() computes realized PnL."""
        entry = self._pending.pop(trade_id, None)
        if entry is None:
            return
        state_vec, action_idx, log_prob, value = entry
        reward = float(np.tanh(pnl / 100.0))  # normalize to [-1, 1]
        self.agent.store_transition(state_vec, action_idx, reward, log_prob, value, done=True)
        if len(self.agent.buffer) >= self.agent.buffer.buffer_size:
            try:
                self.agent.update()
                self.agent.buffer.clear()
                logger.info("PPO update triggered after buffer fill")
            except Exception as exc:
                logger.warning("PPO update failed: %s", exc)

    # ------------------------------------------------------------------
    # State construction
    # ------------------------------------------------------------------

    def _build_state(self, context: "PaperTradeContext") -> np.ndarray:
        """Build 166-dim state vector from paper trade context."""
        embedding = np.zeros(128, dtype=np.float32)
        energies = np.zeros(5, dtype=np.float32)
        actions = np.zeros(5, dtype=np.float32)
        op_scores = np.zeros(18, dtype=np.float32)

        pnl_hist = self.agent.recent_pnl[-10:] if self.agent.recent_pnl else []
        pnl_vec = np.zeros(10, dtype=np.float32)
        if pnl_hist:
            pnl_vec[-len(pnl_hist):] = pnl_hist

        return np.concatenate([embedding, energies, actions, op_scores, pnl_vec])

    @staticmethod
    def _trade_id(context: "PaperTradeContext") -> str:
        return f"{context.routed_order.symbol}_{int(context.entry_time * 1000)}"
