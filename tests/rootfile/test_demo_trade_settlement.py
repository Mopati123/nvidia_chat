"""Closed-trade settlement tests for MT5 demo feedback."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from data_core.ml.evidence_dataset import read_refusal_risk_dataset
from trading.feedback.demo_settlement import (
    DemoTrade,
    classify_close_reason,
    load_demo_trades,
    settle_demo_trades,
    settle_trade,
)
from trading.rl.ppo_paper_hook import PPOPaperHook
from trading.rl.scheduler_agent import PPOSchedulerAgent


def _trade(ticket: str = "123") -> DemoTrade:
    return DemoTrade(
        ticket=ticket,
        symbol="EURUSD",
        direction="buy",
        entry=1.1000,
        stop=1.0990,
        target=1.1020,
        size=0.01,
        predicted_pnl=0.2,
        source="mt5",
        opened_at="2026-05-04T09:27:26",
        csv_path="demo.csv",
    )


def _deal(ticket: int = 123, *, entry: int = 1, reason: int = 5, profit: float = 1.2):
    return SimpleNamespace(
        position_id=ticket,
        entry=entry,
        profit=profit,
        swap=-0.1,
        commission=-0.05,
        reason=reason,
        time=1777879646,
    )


def _write_csv(path: Path, ticket: str = "123") -> None:
    path.write_text(
        "\n".join([
            "time,symbol,direction,entry,stop,target,size,ticket,predicted_pnl,source",
            f"2026-05-04T09:27:26,EURUSD,buy,1.1,1.099,1.102,0.01,{ticket},0.2,mt5",
            "2026-05-04T09:27:26,EURUSD,buy,1.1,1.099,1.102,0.01,paper,0.2,mt5",
            "",
        ]),
        encoding="utf-8",
    )


def test_settlement_parser_reports_open_position():
    record = settle_trade(_trade(), {123}, [_deal()])

    assert record.status == "open"
    assert record.realized_pnl is None


def test_settlement_parser_reports_missing_history():
    record = settle_trade(_trade(), set(), [])

    assert record.status == "missing_history"
    assert record.realized_pnl is None


def test_settlement_parser_handles_tp_sl_and_manual_reasons():
    assert classify_close_reason(_deal(reason=5)) == "tp"
    assert classify_close_reason(_deal(reason=4)) == "sl"
    assert classify_close_reason(_deal(reason=3)) == "manual"

    record = settle_trade(
        _trade(),
        set(),
        [_deal(entry=0, profit=0.0), _deal(reason=5, profit=1.5)],
    )

    assert record.status == "closed"
    assert record.close_reason == "tp"
    assert record.realized_pnl == 1.2


def test_load_demo_trades_skips_paper_and_non_numeric_tickets(tmp_path: Path):
    csv_path = tmp_path / "demo.csv"
    _write_csv(csv_path)

    trades = load_demo_trades([csv_path])

    assert [trade.ticket for trade in trades] == ["123"]


def test_settle_demo_trades_writes_ledger_evidence_and_ml_artifacts(tmp_path: Path):
    csv_path = tmp_path / "demo.csv"
    ledger_path = tmp_path / "settlements.jsonl"
    evidence_path = tmp_path / "evidence.jsonl"
    dataset_path = tmp_path / "refusal_risk.parquet"
    model_path = tmp_path / "model.json"
    _write_csv(csv_path)

    report = settle_demo_trades(
        trade_patterns=[csv_path],
        ledger_path=ledger_path,
        evidence_log_path=evidence_path,
        ppo_checkpoint_path=tmp_path / "ppo.pt",
        ppo_pending_path=tmp_path / "pending.json",
        dataset_path=dataset_path,
        model_path=model_path,
        positions=[],
        history_deals=[_deal(entry=0, profit=0.0), _deal()],
    )

    assert report.scanned == 1
    assert report.closed == 1
    assert report.records[0].ppo_feedback_status == "missing_pending_state"
    assert ledger_path.exists()
    assert evidence_path.exists()
    assert dataset_path.exists()
    assert model_path.exists()
    rows = read_refusal_risk_dataset(dataset_path)
    assert rows[0]["realized_pnl"] == 0.9
    assert rows[0]["close_reason"] == "tp"
    assert json.loads(model_path.read_text(encoding="utf-8"))["runtime_integration"] == "offline_only"


def test_settle_demo_trades_tolerates_malformed_ppo_pending_json(tmp_path: Path):
    csv_path = tmp_path / "demo.csv"
    pending_path = tmp_path / "pending.json"
    _write_csv(csv_path)
    pending_path.write_text("{not valid json", encoding="utf-8")

    report = settle_demo_trades(
        trade_patterns=[csv_path],
        ledger_path=tmp_path / "settlements.jsonl",
        evidence_log_path=tmp_path / "evidence.jsonl",
        ppo_checkpoint_path=tmp_path / "ppo.pt",
        ppo_pending_path=pending_path,
        dataset_path=tmp_path / "refusal_risk.parquet",
        model_path=tmp_path / "model.json",
        positions=[],
        history_deals=[_deal(entry=0, profit=0.0), _deal()],
    )

    assert report.closed == 1
    assert report.records[0].ppo_feedback_status == "missing_pending_state"


def test_settle_demo_trades_tolerates_empty_ppo_pending_json(tmp_path: Path):
    csv_path = tmp_path / "demo.csv"
    pending_path = tmp_path / "pending.json"
    _write_csv(csv_path)
    pending_path.write_text("", encoding="utf-8")

    report = settle_demo_trades(
        trade_patterns=[csv_path],
        ledger_path=tmp_path / "settlements.jsonl",
        evidence_log_path=tmp_path / "evidence.jsonl",
        ppo_checkpoint_path=tmp_path / "ppo.pt",
        ppo_pending_path=pending_path,
        dataset_path=tmp_path / "refusal_risk.parquet",
        model_path=tmp_path / "model.json",
        positions=[],
        history_deals=[_deal(entry=0, profit=0.0), _deal()],
    )

    assert report.closed == 1
    assert report.records[0].ppo_feedback_status == "missing_pending_state"


def test_ppo_checkpoint_and_pending_state_round_trip(tmp_path: Path):
    checkpoint_path = tmp_path / "ppo.pt"
    pending_path = tmp_path / "pending.json"
    agent = PPOSchedulerAgent(batch_size=8, buffer_size=16, device="cpu")
    hook = PPOPaperHook(agent)

    context = SimpleNamespace(
        status="executed",
        trade_id="123",
        routed_order=SimpleNamespace(symbol="EURUSD"),
        entry_time=1.0,
        selected_path={"S_L": 0.1, "S_T": 0.2, "S_E": 0.3, "S_R": 0.4, "energy": 0.5},
        action_weights={"L": 0.5, "T": 0.3, "E": 0.1, "R": 0.1},
        operator_scores={},
        memory_embedding=np.zeros(128, dtype=np.float32),
    )

    hook.on_trade_executed(context)
    agent.save(str(checkpoint_path))
    pending_path.write_text(json.dumps(hook.export_pending()), encoding="utf-8")

    restored = PPOSchedulerAgent(batch_size=8, buffer_size=16, device="cpu")
    restored.load(str(checkpoint_path))
    restored_hook = PPOPaperHook(restored)
    imported = restored_hook.import_pending(json.loads(pending_path.read_text(encoding="utf-8")))

    assert imported == 1
    assert restored_hook.has_pending("123")
    assert restored_hook.on_trade_closed("123", 2.5) is True
