"""Token-flow tests for rootfile execution boundaries."""

import random

import numpy as np

from apps.telegram.trading_live import LiveTradingSystem
from core.authority.execution_token import issue_execution_token
from core.execution.shadow import execute_shadow_authorized
from trading.kernel.apex_engine import ExecutionOutcome


def make_ohlcv(n: int = 24) -> list[dict]:
    random.seed(12345)
    np.random.seed(12345)
    price = 1.0850
    candles = []
    for i in range(n):
        change = 0.0001 if i % 2 == 0 else -0.00003
        open_p = price
        close_p = price + change
        candles.append({
            "open": round(open_p, 5),
            "high": round(max(open_p, close_p) + 0.0002, 5),
            "low": round(min(open_p, close_p) - 0.0002, 5),
            "close": round(close_p, 5),
            "volume": 1000 + i * 10,
            "timestamp": i,
        })
        price = close_p
    return candles


class StaticFeed:
    def fetch_ohlcv(self, *args, **kwargs):
        return make_ohlcv()


def test_shadow_execution_refuses_missing_token():
    execution = execute_shadow_authorized(
        "EURUSD",
        make_ohlcv(),
        "bullish",
        "london",
        token=None,
    )

    assert execution.outcome == ExecutionOutcome.REFUSED
    assert execution.evidence_hash
    assert execution.execution_id.startswith("shadow_refused")


def test_shadow_execution_accepts_authorized_token():
    token = issue_execution_token("shadow_execution", budget=1.0)

    execution = execute_shadow_authorized(
        "EURUSD",
        make_ohlcv(),
        "bullish",
        "london",
        token=token,
    )

    assert execution.outcome in {ExecutionOutcome.SUCCESS, ExecutionOutcome.REFUSED}
    assert execution.evidence_hash
    assert not execution.execution_id.startswith("shadow_refused")


def test_live_trading_system_blocks_missing_token_before_data_fetch():
    system = LiveTradingSystem()
    system.data_feed = StaticFeed()

    result = system.execute_trade("EURUSD", "buy", 0.01, token=None)

    assert result["blocked"] is True
    assert "token" in result["error"]


def test_live_trading_system_accepts_authorized_shadow_token():
    system = LiveTradingSystem()
    system.data_feed = StaticFeed()
    token = issue_execution_token("live_execution", budget=1.0)

    result = system.execute_trade("EURUSD", "buy", 0.01, token=token)

    assert not result.get("blocked", False)
    assert result["mode"] == "shadow"
    assert result["evidence_hash"]

