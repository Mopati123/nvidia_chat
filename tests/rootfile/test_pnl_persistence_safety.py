"""Fail-closed PnL persistence safety tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import trading.risk.pnl_tracker as pnl_module
import trading.risk.risk_manager as risk_module
from trading.risk.pnl_tracker import DailyPnLTracker, TradeRecord


def _reset_risk_singletons(monkeypatch):
    monkeypatch.setattr(risk_module, "risk_manager", None)
    monkeypatch.setattr(pnl_module, "pnl_tracker", None)


def _state_path(data_dir: Path) -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    return data_dir / f"pnl_{today}.json"


def _trade(trade_id: str = "t1") -> TradeRecord:
    return TradeRecord(
        trade_id=trade_id,
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1,
        exit_price=1.2,
        size=0.01,
        realized_pnl=1.0,
        entry_time=1.0,
        exit_time=2.0,
        broker="paper",
    )


@pytest.mark.parametrize("contents", ["{not-json", ""])
def test_corrupt_or_truncated_pnl_state_fails_closed(monkeypatch, tmp_path, contents):
    _reset_risk_singletons(monkeypatch)
    _state_path(tmp_path).write_text(contents, encoding="utf-8")

    tracker = DailyPnLTracker(data_dir=str(tmp_path))

    assert tracker.persistence_healthy is False
    assert "failed_to_load_pnl_state" in str(tracker.persistence_error)
    assert tracker.get_daily_stats()["persistence_healthy"] is False

    risk_check = tracker.risk_manager.check_all_limits("EURUSD", "buy", 0.01, 1.1)
    assert risk_check.passed is False
    assert risk_check.metric == "kill_switch"

    with pytest.raises(RuntimeError, match="PnL persistence unhealthy"):
        tracker.record_trade(_trade())


def test_atomic_pnl_save_preserves_old_state_when_replace_fails(monkeypatch, tmp_path):
    _reset_risk_singletons(monkeypatch)
    old_payload = {"date": datetime.now(timezone.utc).date().isoformat(), "daily_pnl": 0.0}
    state_path = _state_path(tmp_path)
    state_path.write_text(json.dumps(old_payload), encoding="utf-8")
    tracker = DailyPnLTracker(data_dir=str(tmp_path))

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(pnl_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        tracker._save_state()

    assert json.loads(state_path.read_text(encoding="utf-8")) == old_payload
    assert tracker.persistence_healthy is False
    assert tracker.risk_manager.manual_kill_switch is True


def test_daily_summary_write_is_atomic_and_valid_json(monkeypatch, tmp_path):
    _reset_risk_singletons(monkeypatch)
    tracker = DailyPnLTracker(data_dir=str(tmp_path))
    tracker.daily_trades.append(_trade())
    tracker.daily_pnl = 1.0

    tracker._archive_daily_summary()

    summary_path = tmp_path / f"summary_{tracker.current_date.isoformat()}.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["total_pnl"] == 1.0
    assert not list(tmp_path.glob("*.tmp"))
