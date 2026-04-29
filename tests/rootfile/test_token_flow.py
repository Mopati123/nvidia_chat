"""Token-flow tests for rootfile execution boundaries."""

import json
import random
from pathlib import Path

import numpy as np

from apps.telegram.trading_live import LiveTradingSystem
from core.authority.execution_token import issue_execution_token, issue_hft_execution_token
from core.authority.hft_token import HFTExecutionScope
from core.authority.token_validator import validate_token
from core.execution.hft import (
    FakeHFTBroker,
    HFTOrderRequest,
    HFTRiskLimits,
    HFTSandboxGateway,
)
from core.execution.shadow import execute_shadow_authorized
from tachyonic_chain.audit_log import append_execution_evidence, verify_execution_evidence_chain
from tools.token_flow_validator import TokenFlowValidator
from trading.brokers.deriv_broker import DerivBroker, DerivOrder
import trading.brokers.mt5_broker as mt5_module
from trading.brokers.mt5_broker import MT5Broker, MT5Order
from trading.kernel.apex_engine import ExecutionOutcome
from trading.kernel.scheduler import Scheduler


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


def test_direct_mt5_order_refuses_missing_token_before_terminal_check(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("APEX_EVIDENCE_LOG", str(tmp_path / "evidence.jsonl"))

    def fail_account_info():
        raise AssertionError("MT5 terminal should not be touched without a token")

    monkeypatch.setattr(mt5_module.mt5, "account_info", fail_account_info)
    broker = MT5Broker()
    order = MT5Order(symbol="EURUSD", order_type="buy", volume=0.01)

    assert broker.place_order(order, token=None) is None

    records = (tmp_path / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    assert records
    assert json.loads(records[-1])["outcome"] == "refused"


def test_direct_deriv_contract_refuses_missing_token_before_api_call(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("APEX_EVIDENCE_LOG", str(tmp_path / "evidence.jsonl"))

    class GuardedDeriv(DerivBroker):
        def _send_request(self, request):
            raise AssertionError("Deriv API should not be touched without a token")

    broker = GuardedDeriv()
    order = DerivOrder("frxEURUSD", "CALL", 1.0, 5, "m")

    assert broker.place_contract(order, token=None) is None

    records = (tmp_path / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    assert records
    assert json.loads(records[-1])["outcome"] == "refused"


def test_audit_log_hash_chains_execution_records(tmp_path: Path):
    log_path = tmp_path / "evidence.jsonl"

    first = append_execution_evidence(
        event_type="test_refusal",
        execution_id="exec_1",
        operation="live_execution",
        outcome="refused",
        token_status="missing execution token",
        log_path=log_path,
    )
    second = append_execution_evidence(
        event_type="test_execution",
        execution_id="exec_2",
        operation="live_execution",
        outcome="success",
        token_status="authorized",
        log_path=log_path,
    )

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["record_hash"] == first
    assert records[1]["previous_hash"] == first
    assert records[1]["record_hash"] == second


def test_token_flow_validator_accepts_direct_broker_boundaries():
    validator = TokenFlowValidator()

    assert validator.validate_file("trading/brokers/mt5_broker.py").valid
    assert validator.validate_file("trading/brokers/deriv_broker.py").valid


def _hft_scope(**overrides):
    values = {
        "broker": "fake",
        "symbol": "BTCUSDT",
        "side": "buy",
        "max_notional": 50.0,
        "max_slippage_bps": 2.0,
        "max_order_count": 2,
        "ttl_seconds": 60.0,
        "strategy_id": "test_depth_accumulation",
        "sandbox_only": True,
    }
    values.update(overrides)
    return HFTExecutionScope(**values)


def _hft_request(**overrides):
    values = {
        "broker": "fake",
        "symbol": "BTCUSDT",
        "side": "buy",
        "quantity": 0.1,
        "price": 100.0,
        "max_slippage_bps": 1.0,
        "strategy_id": "test_depth_accumulation",
        "idempotency_key": "idem_1",
    }
    values.update(overrides)
    return HFTOrderRequest(**values)


def test_live_execution_token_cannot_authorize_hft_execution():
    token = issue_execution_token("live_execution", budget=1.0)

    result = validate_token(token, operation="hft_execution", context=_hft_request().validation_context())

    assert not result.valid
    assert "does not authorize" in result.reason


def test_scheduler_issued_hft_token_accepts_sandbox_fake_order(tmp_path: Path):
    scheduler = Scheduler()
    token = issue_hft_execution_token(scheduler, _hft_scope())
    gateway = HFTSandboxGateway(evidence_log=str(tmp_path / "hft.jsonl"))

    result = gateway.execute(_hft_request(), token=token, feed_health={"stale": False, "update_age_seconds": 0.1})

    assert result.accepted is True
    assert result.outcome == "accepted"
    assert result.order_id
    assert result.evidence_hash
    assert gateway.broker.orders
    assert verify_execution_evidence_chain(tmp_path / "hft.jsonl").valid


def test_hft_gateway_refuses_missing_wrong_and_expired_tokens(tmp_path: Path):
    scheduler = Scheduler()
    expired = issue_hft_execution_token(scheduler, _hft_scope(ttl_seconds=-1.0))
    wrong_symbol = issue_hft_execution_token(scheduler, _hft_scope(symbol="ETHUSDT"))
    gateway = HFTSandboxGateway(evidence_log=str(tmp_path / "hft.jsonl"))
    request = _hft_request()

    assert gateway.execute(request, token=None).outcome == "refused"
    assert gateway.execute(_hft_request(idempotency_key="idem_2"), token=expired).outcome == "refused"
    wrong = gateway.execute(_hft_request(idempotency_key="idem_3"), token=wrong_symbol)

    assert wrong.outcome == "refused"
    assert "symbol" in wrong.reason
    assert not gateway.broker.orders
    assert verify_execution_evidence_chain(tmp_path / "hft.jsonl").valid


def test_hft_hard_limits_block_unsafe_orders_and_kill_switch(tmp_path: Path):
    scheduler = Scheduler()
    token = issue_hft_execution_token(scheduler, _hft_scope(max_notional=100.0, max_order_count=5))
    gateway = HFTSandboxGateway(
        limits=HFTRiskLimits(
            max_orders_per_minute=1,
            max_open_notional=20.0,
            per_symbol_exposure=20.0,
            stale_feed_cutoff_seconds=0.5,
            max_slippage_bps=2.0,
        ),
        evidence_log=str(tmp_path / "hft.jsonl"),
    )

    stale = gateway.execute(_hft_request(idempotency_key="stale"), token=token, feed_health={"stale": True})
    slippage = gateway.execute(
        _hft_request(idempotency_key="slip", max_slippage_bps=3.0),
        token=token,
        feed_health={"stale": False, "update_age_seconds": 0.1},
    )
    accepted = gateway.execute(
        _hft_request(idempotency_key="ok"),
        token=token,
        feed_health={"stale": False, "update_age_seconds": 0.1},
    )
    rate_limited = gateway.execute(
        _hft_request(idempotency_key="rate"),
        token=token,
        feed_health={"stale": False, "update_age_seconds": 0.1},
    )
    gateway.trigger_kill_switch("test")
    killed = gateway.execute(
        _hft_request(idempotency_key="kill"),
        token=token,
        feed_health={"stale": False, "update_age_seconds": 0.1},
    )

    assert stale.reason == "stale_feed"
    assert slippage.reason == "hft token slippage limit exceeded"
    assert accepted.outcome == "accepted"
    assert rate_limited.reason == "orders_per_minute_limit_exceeded"
    assert killed.reason == "kill_switch_active"
    assert verify_execution_evidence_chain(tmp_path / "hft.jsonl").valid


def test_hft_idempotency_prevents_duplicate_submission(tmp_path: Path):
    scheduler = Scheduler()
    token = issue_hft_execution_token(scheduler, _hft_scope())
    broker = FakeHFTBroker()
    gateway = HFTSandboxGateway(broker=broker, evidence_log=str(tmp_path / "hft.jsonl"))
    request = _hft_request(idempotency_key="same")

    first = gateway.execute(request, token=token, feed_health={"stale": False, "update_age_seconds": 0.1})
    duplicate = gateway.execute(request, token=token, feed_health={"stale": False, "update_age_seconds": 0.1})

    assert first.outcome == "accepted"
    assert duplicate.outcome == "refused"
    assert duplicate.reason == "duplicate_idempotency_key"
    assert len(broker.orders) == 1
    assert verify_execution_evidence_chain(tmp_path / "hft.jsonl").valid


def test_hft_failed_canceled_and_reconciled_paths_emit_evidence(tmp_path: Path):
    scheduler = Scheduler()
    token = issue_hft_execution_token(scheduler, _hft_scope(max_order_count=5))
    gateway = HFTSandboxGateway(
        broker=FakeHFTBroker(fail_next=True),
        evidence_log=str(tmp_path / "hft.jsonl"),
    )
    failed = gateway.execute(
        _hft_request(idempotency_key="fail"),
        token=token,
        feed_health={"stale": False, "update_age_seconds": 0.1},
    )

    accepted_request = _hft_request(idempotency_key="accept")
    accepted = gateway.execute(
        accepted_request,
        token=token,
        feed_health={"stale": False, "update_age_seconds": 0.1},
    )
    canceled = gateway.cancel_order(accepted_request, token=token, order_id=accepted.order_id)
    reconciled = gateway.reconcile_order(accepted_request, order_id=accepted.order_id, realized_pnl=1.23)

    assert failed.outcome == "failed"
    assert canceled.outcome == "canceled"
    assert reconciled.outcome == "reconciled"
    report = verify_execution_evidence_chain(tmp_path / "hft.jsonl")
    assert report.valid
