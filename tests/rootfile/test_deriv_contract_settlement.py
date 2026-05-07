"""Closed-contract settlement tests for Deriv demo feedback."""

from __future__ import annotations

import json
from pathlib import Path

from data_core.ml.evidence_dataset import read_refusal_risk_dataset
from tachyonic_chain.audit_log import verify_execution_evidence_chain
from trading.brokers.deriv_broker import DerivBroker
from trading.feedback.deriv_settlement import (
    DerivContractTrade,
    load_deriv_contract_trades,
    settle_deriv_contract,
    settle_deriv_contracts,
)
from trading.rl.scheduler_agent import PPOSchedulerAgent


def _write_csv(path: Path, contract_id: str = "777") -> None:
    path.write_text(
        "\n".join([
            "time,symbol,direction,entry,stop,target,size,ticket,predicted_pnl,source",
            f"2026-05-05T10:00:00,EURUSD,buy,1.1000,1.0990,1.1020,0.01,{contract_id},0.2,deriv",
            "2026-05-05T10:01:00,EURUSD,buy,1.1000,1.0990,1.1020,0.01,ord_1,0.2,deriv",
            "2026-05-05T10:02:00,EURUSD,buy,1.1000,1.0990,1.1020,0.01,123,0.2,mt5",
            "",
        ]),
        encoding="utf-8",
    )


def _trade(contract_id: str = "777") -> DerivContractTrade:
    return DerivContractTrade(
        contract_id=contract_id,
        symbol="EURUSD",
        direction="buy",
        entry=1.1000,
        stop=1.0990,
        target=1.1020,
        size=0.01,
        predicted_pnl=0.2,
        source="deriv",
        opened_at="2026-05-05T10:00:00",
        csv_path="demo.csv",
    )


def _closed_status(contract_id: str = "777", *, status: str = "won", profit: float | str = "0.95"):
    return {
        "contract_id": contract_id,
        "contract_type": "CALL",
        "status": status,
        "is_expired": 1,
        "is_sold": 1,
        "buy_price": "1.00",
        "sell_price": "1.95" if status == "won" else "0.00",
        "profit": profit,
        "exit_spot_time": 1777975200,
    }


def _pending_payload(contract_id: str) -> dict:
    return {
        contract_id: {
            "state": [0.0] * 166,
            "action_idx": 0,
            "log_prob": 0.0,
            "value": 0.0,
        }
    }


def test_load_deriv_contract_trades_skips_paper_and_mt5_rows(tmp_path: Path):
    csv_path = tmp_path / "demo.csv"
    _write_csv(csv_path, "777")

    trades = load_deriv_contract_trades([csv_path])

    assert [trade.contract_id for trade in trades] == ["777"]
    assert trades[0].source == "deriv"


def test_deriv_contract_status_request_is_read_only_without_invalid_subscribe():
    class FakeDerivBroker(DerivBroker):
        def __init__(self):
            self.connected = True
            self.authorized = True
            self.sent = None

        def _send_request(self, request):
            self.sent = request
            return {"proposal_open_contract": {"contract_id": 777, "status": "open"}}

    broker = FakeDerivBroker()

    status = broker.get_contract_status("777")

    assert status == {"contract_id": 777, "status": "open"}
    assert broker.sent == {"proposal_open_contract": 1, "contract_id": 777}


def test_deriv_settlement_parser_reports_open_contract():
    record = settle_deriv_contract(_trade("777"), {"777"}, {}, [])

    assert record.status == "open"
    assert record.realized_pnl is None


def test_deriv_settlement_parser_reports_missing_history():
    record = settle_deriv_contract(_trade("777"), set(), {}, [])

    assert record.status == "missing_history"


def test_deriv_settlement_parser_handles_closed_win_from_contract_status():
    record = settle_deriv_contract(
        _trade("777"),
        set(),
        {"777": _closed_status("777", status="won", profit="0.95")},
        [],
    )

    assert record.status == "closed"
    assert record.close_reason == "won"
    assert record.realized_pnl == 0.95
    assert record.buy_price == 1.0
    assert record.sell_price == 1.95


def test_deriv_settlement_parser_handles_closed_loss_from_profit_table_fallback():
    record = settle_deriv_contract(
        _trade("888"),
        set(),
        {},
        [{
            "contract_id": "888",
            "contract_type": "PUT",
            "status": "lost",
            "buy_price": "1.00",
            "sell_price": "0.00",
        }],
    )

    assert record.status == "closed"
    assert record.close_reason == "lost"
    assert record.contract_type == "PUT"
    assert record.realized_pnl == -1.0


def test_deriv_settlement_uses_profit_without_treating_payout_as_sell_price():
    record = settle_deriv_contract(
        _trade("999"),
        set(),
        {},
        [{
            "contract_id": "999",
            "contract_type": "CALL",
            "status": "lost",
            "buy_price": "1.00",
            "payout": "1.41",
            "profit": "-1.00",
        }],
    )

    assert record.status == "closed"
    assert record.realized_pnl == -1.0
    assert record.sell_price is None


def test_settle_deriv_contracts_skips_already_settled_contract(tmp_path: Path):
    csv_path = tmp_path / "demo.csv"
    ledger_path = tmp_path / "ledger.jsonl"
    evidence_path = tmp_path / "evidence.jsonl"
    _write_csv(csv_path, "777")
    ledger_path.write_text(
        json.dumps({"contract_id": "777", "status": "closed"}) + "\n",
        encoding="utf-8",
    )

    report = settle_deriv_contracts(
        trade_patterns=[csv_path],
        ledger_path=ledger_path,
        evidence_log_path=evidence_path,
        active_contracts=[],
        contract_statuses={"777": _closed_status("777")},
        profit_table=[],
        rebuild_ml=False,
    )

    assert report.closed == 1
    assert report.already_settled == 1
    assert report.records[0].ppo_feedback_status == "already_settled"
    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 1
    assert not evidence_path.exists()


def test_settle_deriv_contracts_writes_ledger_evidence_and_ml_artifacts(tmp_path: Path):
    csv_path = tmp_path / "demo.csv"
    ledger_path = tmp_path / "settlements.jsonl"
    evidence_path = tmp_path / "evidence.jsonl"
    dataset_path = tmp_path / "data" / "evidence_dataset" / "refusal_risk.parquet"
    model_path = tmp_path / "data" / "models" / "refusal_risk_model.json"
    checkpoint_path = tmp_path / "data" / "models" / "ppo_live_demo.pt"
    pending_path = tmp_path / "data" / "models" / "ppo_live_demo_pending.json"
    _write_csv(csv_path, "777")

    report = settle_deriv_contracts(
        trade_patterns=[csv_path],
        ledger_path=ledger_path,
        evidence_log_path=evidence_path,
        ppo_checkpoint_path=checkpoint_path,
        ppo_pending_path=pending_path,
        dataset_path=dataset_path,
        model_path=model_path,
        active_contracts=[],
        contract_statuses={"777": _closed_status("777", status="won", profit="0.95")},
        profit_table=[],
    )

    assert report.scanned == 1
    assert report.closed == 1
    assert report.records[0].status == "closed"
    assert report.records[0].ppo_feedback_status == "missing_pending_state"
    assert report.records[0].falsification_status == "correct_authorization"
    assert report.records[0].falsification_hash is not None
    assert ledger_path.exists()
    assert verify_execution_evidence_chain(evidence_path).valid
    rows = read_refusal_risk_dataset(dataset_path)
    assert len(rows) == 2
    assert rows[0]["broker"] == "deriv"
    assert rows[0]["realized_pnl"] == 0.95
    assert rows[1]["event_type"] == "falsification_score"
    assert rows[1]["outcome"] == "correct_authorization"
    assert json.loads(model_path.read_text(encoding="utf-8"))["runtime_integration"] == "offline_only"


def test_settle_deriv_contracts_feeds_ppo_when_pending_state_exists(tmp_path: Path):
    csv_path = tmp_path / "demo.csv"
    pending_path = tmp_path / "data" / "models" / "ppo_live_demo_pending.json"
    checkpoint_path = tmp_path / "data" / "models" / "ppo_live_demo.pt"
    _write_csv(csv_path, "999")
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(json.dumps(_pending_payload("999")), encoding="utf-8")

    report = settle_deriv_contracts(
        trade_patterns=[csv_path],
        ledger_path=tmp_path / "settlements.jsonl",
        evidence_log_path=tmp_path / "evidence.jsonl",
        ppo_checkpoint_path=checkpoint_path,
        ppo_pending_path=pending_path,
        dataset_path=tmp_path / "refusal_risk.parquet",
        model_path=tmp_path / "refusal_risk_model.json",
        active_contracts=[],
        contract_statuses={"999": _closed_status("999", status="won", profit="1.25")},
        profit_table=[],
        rebuild_ml=False,
    )

    assert report.records[0].ppo_feedback_status == "transition_stored"
    assert checkpoint_path.exists()
    assert json.loads(pending_path.read_text(encoding="utf-8")) == {}

    restored = PPOSchedulerAgent(device="cpu")
    restored.load(str(checkpoint_path))
    assert len(restored.buffer) == 1
    assert restored.total_steps == 1
    assert restored.recent_pnl
