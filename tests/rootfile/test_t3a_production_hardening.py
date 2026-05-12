"""Focused T3-A production hardening tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tachyonic_chain.audit_log import verify_execution_evidence_chain
from trading.feedback.demo_settlement import settle_demo_trades
from trading.kernel.scheduler import CollapseDecision
from trading.pipeline.orchestrator import PipelineContext, PipelineOrchestrator
from trading.resilience.checkpoints import Checkpoint, load_checkpoint, persist_checkpoint
from trading.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from trading.risk.pnl_tracker import DailyPnLTracker
from trading.risk.risk_manager import Position, ProductionRiskManager


class _RiskManager:
    kill_switch_active = False

    def __init__(self) -> None:
        self.kill_reasons = []

    def trigger_kill_switch(self, reason):
        self.kill_reasons.append(reason)

    def snapshot_state(self):
        return {"manual_kill_switch": False, "positions": {}}


class _Scheduler:
    config = {"max_entropy": 0.5}

    def __init__(self) -> None:
        self.weight_updates = []

    def authorize_collapse(self, **kwargs):
        return CollapseDecision.REFUSED, None

    def update_action_weights(self, **kwargs):
        self.weight_updates.append(kwargs)


def _deal(ticket: int, *, entry: int, reason: int = 4, profit: float = 0.0):
    return SimpleNamespace(
        position_id=ticket,
        entry=entry,
        profit=profit,
        swap=0.0,
        commission=0.0,
        reason=reason,
        time=1777879646,
    )


def test_stage17_live_entry_keeps_pnl_pending_until_close():
    scheduler = _Scheduler()
    orchestrator = PipelineOrchestrator(
        scheduler=scheduler,
        risk_manager=_RiskManager(),
        use_microstructure=False,
        use_weight_learning=False,
    )
    captured = []
    orchestrator._audit_gate = lambda gate, status, **fields: captured.append((gate, status, fields))

    context = PipelineContext(symbol="EURUSD", timestamp=1.0, source="test")
    context.proposal = {"entry": 1.1, "predicted_pnl": 0.4}
    context.execution_result = {
        "entry_price": 1.1,
        "broker": "mt5",
        "status": "filled",
        "realized_pnl": 0.0,
        "pnl_status": "pending_close",
    }
    context.action_scores["delta_s"] = 0.2

    result = orchestrator._stage_reconciliation(context)

    assert result["status"] == "match"
    assert result["pnl_status"] == "pending_close"
    assert result["pnl_divergence"] is None
    assert result["divergence_flagged"] is False
    assert list(orchestrator.divergence_history) == []
    assert scheduler.weight_updates == []
    assert captured[0][2]["pnl_status"] == "pending_close"


def test_settlement_records_closed_trade_divergence_for_mt5_ticket(tmp_path: Path):
    ticket = "357844399"
    csv_path = tmp_path / "demo_trades.csv"
    csv_path.write_text(
        "\n".join([
            "time,symbol,direction,entry,stop,target,size,ticket,predicted_pnl,source",
            f"2026-05-08T10:14:00,EURUSD,buy,1.1,1.099,1.102,0.01,{ticket},0.4,mt5",
            "",
        ]),
        encoding="utf-8",
    )

    report = settle_demo_trades(
        trade_patterns=[csv_path],
        ledger_path=tmp_path / "settlements.jsonl",
        evidence_log_path=tmp_path / "execution_evidence.jsonl",
        ppo_checkpoint_path=tmp_path / "ppo.pt",
        ppo_pending_path=tmp_path / "pending.json",
        dataset_path=tmp_path / "refusal_risk.parquet",
        model_path=tmp_path / "model.json",
        positions=[],
        history_deals=[
            _deal(int(ticket), entry=0, profit=0.0),
            _deal(int(ticket), entry=1, reason=4, profit=-2.05),
        ],
        rebuild_ml=False,
    )

    record = report.records[0]
    assert record.status == "closed"
    assert record.close_reason == "sl"
    assert record.realized_pnl == -2.05
    assert record.execution_error_pct == pytest.approx(2.45)
    assert record.divergence_flagged is True
    assert record.reconciliation_hash is not None

    evidence_path = tmp_path / "execution_evidence.jsonl"
    assert verify_execution_evidence_chain(evidence_path).valid
    events = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
    reconciliation = [event for event in events if event["event_type"] == "closed_trade_reconciliation"]
    assert reconciliation
    assert reconciliation[0]["outcome"] == "flagged"
    assert reconciliation[0]["payload"]["ticket"] == ticket


def test_daily_pnl_tracker_estimates_rolling_execution_error(tmp_path: Path):
    tracker = DailyPnLTracker(data_dir=str(tmp_path), auto_kill=False)

    ratio = tracker.estimate_execution_error({"predicted_pnl": 0.4, "realized_pnl": -2.05})

    assert ratio == pytest.approx(2.45)
    stats = tracker.get_divergence_stats()
    assert stats["count"] == 1
    assert stats["mean"] == pytest.approx(2.45)
    for idx in range(1005):
        tracker.estimate_execution_error(1.0, float(idx))
    assert len(tracker.execution_errors) == 1000


def test_circuit_breaker_half_open_reopen_applies_exponential_timeout():
    breaker = CircuitBreaker(
        "t3a-test",
        CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=1.0,
            backoff_multiplier=2.0,
            max_timeout_seconds=5.0,
        ),
    )

    def fail():
        raise RuntimeError("collapse failed")

    ok, _ = breaker.call(fail)
    assert ok is False
    assert breaker.state == CircuitState.OPEN
    assert breaker.current_timeout_seconds == pytest.approx(1.0)

    breaker.last_state_change -= breaker.current_timeout_seconds
    ok, _ = breaker.call(fail)

    assert ok is False
    assert breaker.state == CircuitState.OPEN
    assert breaker.current_timeout_seconds == pytest.approx(2.0)

    breaker.last_state_change -= breaker.current_timeout_seconds
    ok, _ = breaker.call(lambda: "recovered")
    assert ok is True
    assert breaker.state == CircuitState.HALF_OPEN


def test_checkpoint_hash_round_trip_succeeds(tmp_path: Path):
    checkpoint = Checkpoint.create(
        component="pipeline",
        stage="scheduler_collapse",
        kind="pre",
        payload={"symbol": "EURUSD", "risk_state": {"daily_pnl": 0.0}},
    )

    path = persist_checkpoint(tmp_path, checkpoint)
    loaded = load_checkpoint(path)

    assert loaded.validate()
    assert loaded.payload == checkpoint.payload


def test_tampered_checkpoint_recovery_triggers_kill_switch():
    manager = ProductionRiskManager(daily_loss_limit=100.0, max_position_size=1.0)
    manager.positions["pos-1"] = Position("EURUSD", "buy", 0.1, 1.1, 1.1)
    checkpoint = Checkpoint.create(
        component="risk",
        stage="scheduler_collapse",
        kind="pre",
        payload={"risk_state": manager.snapshot_state()},
    ).to_dict()
    checkpoint["payload"]["risk_state"]["daily_pnl"] = 999.0

    assert manager.recover_from_checkpoint(checkpoint) is False
    assert manager.manual_kill_switch is True
