"""Token-flow tests for rootfile execution boundaries."""

import json
import random
from pathlib import Path

import numpy as np

from apps.telegram.trading_live import LiveTradingSystem
from core.authority.execution_token import issue_execution_token
from core.execution.shadow import execute_shadow_authorized
from tachyonic_chain.audit_log import append_execution_evidence
from tools.token_flow_validator import TokenFlowValidator
from trading.brokers.deriv_broker import DerivBroker, DerivOrder
import trading.brokers.mt5_broker as mt5_module
from trading.brokers.mt5_broker import MT5Broker, MT5Order
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
