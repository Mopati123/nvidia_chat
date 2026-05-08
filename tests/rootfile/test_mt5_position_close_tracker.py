"""MT5 close-tracker feedback tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trading.brokers import mt5_broker
from trading.brokers.mt5_broker import MT5PositionCloseTracker


def _deal(ticket: int = 353158067, *, entry: int = 1, reason: int = 5,
          profit: float = 0.0, swap: float = 0.0, commission: float = 0.0,
          time: int = 1777912994):
    return SimpleNamespace(
        position_id=ticket,
        entry=entry,
        reason=reason,
        profit=profit,
        swap=swap,
        commission=commission,
        time=time,
    )


def test_tracker_uses_full_lifecycle_net_pnl(monkeypatch):
    deals = [
        _deal(entry=0, reason=3, profit=0.0, commission=-0.02, time=1),
        _deal(entry=1, reason=5, profit=2.03, commission=-0.02, time=2),
    ]
    monkeypatch.setattr(mt5_broker.mt5, "history_deals_get", lambda *args: deals)

    tracker = MT5PositionCloseTracker()

    assert tracker._fetch_realized_pnl(353158067, fallback=0.2) == pytest.approx(1.99)


def test_tracker_falls_back_without_closing_deal(monkeypatch):
    deals = [_deal(entry=0, reason=3, profit=0.0, commission=-0.02)]
    monkeypatch.setattr(mt5_broker.mt5, "history_deals_get", lambda *args: deals)

    tracker = MT5PositionCloseTracker()

    assert tracker._fetch_realized_pnl(353158067, fallback=0.2) == 0.2


def test_tracker_close_reason_mapping(monkeypatch):
    tracker = MT5PositionCloseTracker()

    for reason, expected in [(5, "TP"), (4, "SL"), (3, "CLIENT")]:
        deals = [_deal(entry=1, reason=reason)]
        monkeypatch.setattr(mt5_broker.mt5, "history_deals_get", lambda *args, deals=deals: deals)

        assert tracker._fetch_close_reason(353158067) == expected
