"""Deriv live-demo canary readiness tests."""

from __future__ import annotations

import asyncio
import builtins
import csv
import io
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.trading.run_demo_trading as runner
from scripts.trading.run_demo_trading import (
    SessionStats,
    TickAccumulator,
    build_pipeline_handler,
    deriv_live_preflight_blocker,
    deriv_symbol_for,
    live_demo_argument_blocker,
    max_runtime_seconds_for,
    run_tick_loop_until_stopped,
)
from trading.pipeline.orchestrator import (
    PipelineContext,
    PipelineOrchestrator,
    PipelineStage,
    StageResult,
)


def _args(**overrides) -> Namespace:
    values = {
        "live_demo": True,
        "mode": "deriv",
        "symbol": "EURUSD",
        "deriv_stake": 1.0,
        "deriv_duration": 15,
        "deriv_duration_unit": "m",
        "max_contracts": 1,
    }
    values.update(overrides)
    return Namespace(**values)


class _FakeDeriv:
    authorized = True

    def __init__(self, *, loginid: str = "VRTC123", active_contracts=None,
                 available_types=None, quoted_types=None):
        self.loginid = loginid
        self.active_contracts = list(active_contracts or [])
        self.available_types = set(available_types or ("CALL", "PUT"))
        self.quoted_types = set(quoted_types or ("CALL", "PUT"))
        self.proposal_orders = []

    def get_account_info(self):
        return {"loginid": self.loginid, "demo": self.loginid.startswith("VRTC")}

    def get_active_contracts(self):
        return self.active_contracts

    def get_contracts_for(self, symbol):
        return {
            "available": [
                {"contract_type": contract_type, "underlying_symbol": symbol}
                for contract_type in self.available_types
            ]
        }

    def get_proposal_quote(self, order):
        self.proposal_orders.append(order)
        if order.contract_type in self.quoted_types:
            return {"id": f"proposal-{order.contract_type}", "ask_price": order.amount}
        return None


def test_live_demo_both_mode_refuses():
    blocker = live_demo_argument_blocker(_args(mode="both"))

    assert blocker == "live-demo supports exactly --mode mt5 or --mode deriv"


def test_deriv_live_demo_requires_vrtc_account():
    blocker = deriv_live_preflight_blocker(_FakeDeriv(loginid="CR12345"), _args())

    assert blocker == "Deriv account is not a VRTC demo account: CR12345"


def test_deriv_live_demo_active_contracts_block_startup():
    blocker = deriv_live_preflight_blocker(
        _FakeDeriv(active_contracts=[{"contract_id": "abc"}]),
        _args(),
    )

    assert blocker == "active Deriv contract(s) already open: abc"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"deriv_stake": 1.01}, "Deriv stake cap exceeded"),
        ({"deriv_duration": 16}, "Deriv duration cap exceeded"),
        ({"max_contracts": 2}, "Deriv live-demo max-contracts must be 1"),
    ],
)
def test_deriv_live_demo_caps_reject_unsafe_values(overrides, expected):
    blocker = live_demo_argument_blocker(_args(**overrides))

    assert blocker is not None
    assert expected in blocker


def test_deriv_live_demo_preflight_requires_both_call_and_put_quotes():
    fake = _FakeDeriv(quoted_types={"CALL"})

    blocker = deriv_live_preflight_blocker(fake, _args())

    assert blocker == "Deriv no-buy proposal quote unavailable for frxEURUSD 15m: PUT"
    assert [order.contract_type for order in fake.proposal_orders] == ["CALL", "PUT"]


def test_deriv_live_demo_preflight_accepts_offer_aware_15m_quotes():
    fake = _FakeDeriv()

    blocker = deriv_live_preflight_blocker(fake, _args())

    assert blocker is None
    assert [order.contract_type for order in fake.proposal_orders] == ["CALL", "PUT"]
    assert {order.duration for order in fake.proposal_orders} == {15}
    assert {order.duration_unit for order in fake.proposal_orders} == {"m"}


def test_deriv_live_demo_preflight_blocks_missing_contract_type():
    blocker = deriv_live_preflight_blocker(
        _FakeDeriv(available_types={"CALL"}),
        _args(),
    )

    assert blocker == "Deriv contract type(s) unavailable for frxEURUSD: PUT"


def test_deriv_live_demo_defaults_to_ten_minute_runtime_guard():
    assert max_runtime_seconds_for(_args()) == 600.0
    assert max_runtime_seconds_for(_args(max_runtime_seconds=12.5)) == 12.5
    assert max_runtime_seconds_for(_args(live_demo=False, max_runtime_seconds=0.0)) == 0.0


def test_tick_accumulator_mark_run_updates_readiness_under_lock(monkeypatch):
    accumulator = TickAccumulator(window=20, pipeline_interval=10.0, min_ticks=2)
    accumulator.add(1.1, 1.0)
    accumulator.add(1.2, 2.0)

    monkeypatch.setattr(runner.time, "time", lambda: 100.0)
    assert accumulator.ready() is True

    accumulator.mark_run()

    assert accumulator.ready() is False
    assert accumulator.status()["seconds_since_last_run"] == 0.0


def test_deriv_live_stats_surface_refusal_and_stage16_result():
    stats = SessionStats()

    stats.tick()
    stats.accumulator({
        "tick_count": 10,
        "min_ticks": 10,
        "ready": True,
        "pipeline_interval": 60.0,
        "seconds_since_last_run": 61.0,
    })
    stats.pipeline("REFUSED", "risk_gate_not_passed:test")
    stats.execution({"executed": False, "reason": "broker_refusal"})
    stats.set_stop_reason("max_runtime_no_contract")

    snapshot = stats.snapshot()
    summary = stats.format_deriv_live_summary()

    assert snapshot["ticks_received"] == 1
    assert snapshot["pipeline_runs"] == 1
    assert snapshot["refused"] == 1
    assert snapshot["last_refusal_reason"] == "risk_gate_not_passed:test"
    assert snapshot["last_execution_status"] == "failed"
    assert snapshot["last_execution_reason"] == "broker_refusal"
    assert "stop_reason=max_runtime_no_contract" in summary


def test_async_tick_loop_timeout_sets_no_contract_stop_reason():
    class NeverEndingTickLoop:
        def __init__(self):
            self.cancelled = False

        async def run(self, **kwargs):
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    stats = SessionStats()
    tick_loop = NeverEndingTickLoop()

    result = asyncio.run(
        run_tick_loop_until_stopped(
            tick_loop,
            deriv_broker=object(),
            symbol="EURUSD",
            max_runtime_seconds=0.01,
            stats=stats,
        )
    )

    assert result == "max_runtime_no_contract"
    assert tick_loop.cancelled is True
    assert stats.snapshot()["stop_reason"] == "max_runtime_no_contract"


def test_async_tick_loop_timeout_handles_clean_cancellation_return():
    class CleanStoppingTickLoop:
        async def run(self, **kwargs):
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                return

    stats = SessionStats()

    result = asyncio.run(
        run_tick_loop_until_stopped(
            CleanStoppingTickLoop(),
            deriv_broker=object(),
            symbol="EURUSD",
            max_runtime_seconds=0.01,
            stats=stats,
        )
    )

    assert result == "max_runtime_no_contract"
    assert stats.snapshot()["stop_reason"] == "max_runtime_no_contract"


class _TrackedOpen:
    def __init__(self, handle):
        self._handle = handle
        self.closed = False

    def __getattr__(self, name):
        return getattr(self._handle, name)

    def close(self):
        self.closed = True
        return self._handle.close()


def _patch_runner_main_for_paper_mode(monkeypatch, tmp_path: Path, build_handler):
    opened = []
    real_open = builtins.open

    def tracking_open(file, *args, **kwargs):
        handle = real_open(file, *args, **kwargs)
        if "demo_trades_" in str(file):
            tracked = _TrackedOpen(handle)
            opened.append(tracked)
            return tracked
        return handle

    class FakeRiskManager:
        max_position_size = 0.01

        def get_status(self):
            return {
                "daily_pnl": 0.0,
                "kill_switch": False,
                "level": "green",
                "daily_loss_limit": 20.0,
                "remaining_limit": 20.0,
            }

    class FakeOrchestrator:
        def __init__(self):
            self.risk_manager = FakeRiskManager()
            self._paper_mode = True
            self.live_broker_mode = None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_demo_trading.py", "--mode", "paper"])
    monkeypatch.setattr(builtins, "open", tracking_open)
    monkeypatch.setattr(
        "trading.pipeline.orchestrator.PipelineOrchestrator",
        FakeOrchestrator,
    )
    monkeypatch.setitem(
        sys.modules,
        "trading.rl.scheduler_agent",
        SimpleNamespace(PPOSchedulerAgent=lambda: (_ for _ in ()).throw(RuntimeError("ppo off"))),
    )
    monkeypatch.setattr(runner, "build_pipeline_handler", build_handler)
    monkeypatch.setattr(runner, "status_printer", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner.SessionStats, "print_status", lambda *args, **kwargs: None)
    return opened


def test_runner_closes_trade_log_on_clean_paper_stop(monkeypatch, tmp_path):
    def build_handler(*args, **kwargs):
        return lambda tick: None

    opened = _patch_runner_main_for_paper_mode(monkeypatch, tmp_path, build_handler)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    runner.main()

    assert opened
    assert opened[-1].closed is True


def test_runner_closes_trade_log_when_handler_setup_raises(monkeypatch, tmp_path):
    def build_handler(*args, **kwargs):
        raise RuntimeError("handler setup failed")

    opened = _patch_runner_main_for_paper_mode(monkeypatch, tmp_path, build_handler)

    with pytest.raises(RuntimeError, match="handler setup failed"):
        runner.main()

    assert opened
    assert opened[-1].closed is True


def test_deriv_live_authorized_broker_refusal_does_not_write_trade_row():
    class ReadyAccumulator:
        min_ticks = 10
        pipeline_interval = 60.0

        def add(self, price, ts):
            pass

        def ready(self):
            return True

        def status(self):
            return {
                "tick_count": 10,
                "min_ticks": 10,
                "ready": True,
                "pipeline_interval": 60.0,
                "seconds_since_last_run": 61.0,
            }

        def mark_run(self):
            pass

        def to_ohlcv(self):
            return {
                "open": [1.1],
                "high": [1.1],
                "low": [1.1],
                "close": [1.1],
                "volume": [1],
                "time": [1.0],
            }

    context = SimpleNamespace(
        collapse_decision="AUTHORIZED",
        proposal={
            "direction": "buy",
            "entry": 1.1,
            "stop": 1.0,
            "target": 1.2,
            "size": 0.01,
            "predicted_pnl": 0.2,
        },
        execution_result={},
        stage_history=[
            StageResult(
                stage=PipelineStage.EXECUTION,
                success=True,
                output={"executed": False, "reason": "broker_refusal"},
            )
        ],
    )
    stats = SessionStats()
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=[
        "time", "symbol", "direction", "entry", "stop", "target",
        "size", "ticket", "predicted_pnl", "source",
    ])
    writer.writeheader()

    handler = build_pipeline_handler(
        SimpleNamespace(execute=lambda raw_data, symbol, source: context),
        None,
        ReadyAccumulator(),
        stats,
        "EURUSD",
        "deriv",
        csv_writer=writer,
        live_mode=True,
        live_broker="deriv",
        deriv_broker_ref=SimpleNamespace(get_active_contracts=lambda: []),
    )

    handler(("deriv", {"price": 1.1}))

    assert len(csv_buffer.getvalue().splitlines()) == 1
    snapshot = stats.snapshot()
    assert snapshot["authorized"] == 1
    assert snapshot["last_execution_status"] == "failed"
    assert snapshot["last_execution_reason"] == "broker_refusal"


def _orch() -> PipelineOrchestrator:
    risk_manager = SimpleNamespace(
        kill_switch_active=False,
        trigger_kill_switch=lambda reason: None,
    )
    scheduler = SimpleNamespace(release_execution_token=lambda token: None)
    return PipelineOrchestrator(scheduler=scheduler, risk_manager=risk_manager)


def test_stage19_audit_uses_reconciliation_status_field(monkeypatch):
    scheduler = SimpleNamespace(
        release_execution_token=lambda token: None,
        update_action_weights=lambda **kwargs: {
            "updated": True,
            "reward": 1.0,
            "new_weights": {"L": 25, "T": 25, "E": 25, "R": 25},
        },
    )
    orch = PipelineOrchestrator(
        scheduler=scheduler,
        risk_manager=SimpleNamespace(
            kill_switch_active=False,
            trigger_kill_switch=lambda reason: None,
        ),
    )
    captured = []
    monkeypatch.setattr(
        orch,
        "_audit_gate",
        lambda gate, status, **fields: captured.append((gate, status, fields)),
    )
    context = SimpleNamespace(
        symbol="EURUSD",
        collapse_decision="AUTHORIZED",
        reconciliation_status="match",
        selected_path=None,
        action_scores={},
        risk_check_passed=True,
        evidence_hash="abc",
    )

    orch._stage_weight_update(context)

    gate, status, fields = captured[-1]
    assert gate == "stage19_weight_update"
    assert status == "passed"
    assert fields["reconciliation_status"] == "match"
    assert "status" not in fields


@pytest.mark.parametrize(("direction", "contract_type"), [("buy", "CALL"), ("sell", "PUT")])
def test_deriv_stage16_order_construction_is_deterministic(monkeypatch, direction, contract_type):
    import trading.brokers.deriv_broker as deriv_module

    captured = {}

    class ConnectedDeriv:
        connected = True

        def place_contract(self, order, token=None):
            captured["order"] = order
            captured["token"] = token
            return {"contract_id": "contract-1", "buy_price": order.amount}

    monkeypatch.setattr(deriv_module, "deriv_broker", ConnectedDeriv())
    orch = _orch()
    orch._paper_mode = False
    orch.live_broker_mode = "deriv"
    orch.deriv_live_config = {
        "stake": 1.0,
        "duration": 15,
        "duration_unit": "m",
        "max_contracts": 1,
    }
    token = object()
    context = PipelineContext(symbol="EURUSD", timestamp=1.0, source="DERIV")
    context.collapse_decision = "AUTHORIZED"
    context.execution_token = token
    context.proposal = {
        "direction": direction,
        "entry": 1.1,
        "stop": 1.0,
        "target": 1.2,
        "size": 0.01,
    }

    result = orch._stage_execution(context)

    order = captured["order"]
    assert result["executed"] is True
    assert captured["token"] is token
    assert order.contract_type == contract_type
    assert order.symbol == deriv_symbol_for("EURUSD")
    assert order.amount == 1.0
    assert order.duration == 15
    assert order.duration_unit == "m"
    assert context.execution_result["broker"] == "deriv"


def test_deriv_canary_persists_ppo_pending_before_stop(monkeypatch, tmp_path):
    class ReadyAccumulator:
        def add(self, price, ts):
            pass

        def ready(self):
            return True

        def mark_run(self):
            pass

        def to_ohlcv(self):
            return {
                "open": [1.1],
                "high": [1.1],
                "low": [1.1],
                "close": [1.1],
                "volume": [1],
                "time": [1.0],
            }

    class FakeAgent:
        def save(self, path):
            tmp_path.joinpath("agent_saved").write_text(path, encoding="utf-8")

    class FakePPOHook:
        def __init__(self):
            self.agent = FakeAgent()
            self.pending = {}

        def on_trade_executed(self, context):
            self.pending[str(context.trade_id)] = {"state": [0.0], "action_idx": 0}

        def export_pending(self):
            return self.pending

        def pending_count(self):
            return len(self.pending)

    context = SimpleNamespace(
        collapse_decision="AUTHORIZED",
        proposal={
            "direction": "buy",
            "entry": 1.1,
            "stop": 1.0,
            "target": 1.2,
            "size": 0.01,
            "predicted_pnl": 0.2,
        },
        execution_result={"order_id": "313660691488", "broker": "deriv"},
        selected_path={},
        action_weights={},
        memory_embedding=None,
    )
    orch = SimpleNamespace(execute=lambda raw_data, symbol, source: context)
    pending_path = tmp_path / "ppo_pending.json"
    checkpoint_path = tmp_path / "ppo.pt"
    kill_calls = []

    def fake_kill(pid, sig):
        kill_calls.append((pid, sig))
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        assert "313660691488" in pending

    monkeypatch.setattr("scripts.trading.run_demo_trading.os.kill", fake_kill)

    handler = build_pipeline_handler(
        orch,
        FakePPOHook(),
        ReadyAccumulator(),
        SessionStats(),
        "EURUSD",
        "deriv",
        live_mode=True,
        live_broker="deriv",
        deriv_broker_ref=SimpleNamespace(get_active_contracts=lambda: []),
        ppo_checkpoint_path=checkpoint_path,
        ppo_pending_path=pending_path,
    )

    handler(("deriv", {"price": 1.1}))

    assert kill_calls
