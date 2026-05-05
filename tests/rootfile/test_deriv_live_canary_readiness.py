"""Deriv live-demo canary readiness tests."""

from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest

from scripts.trading.run_demo_trading import (
    deriv_live_preflight_blocker,
    deriv_symbol_for,
    live_demo_argument_blocker,
)
from trading.pipeline.orchestrator import PipelineContext, PipelineOrchestrator


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
