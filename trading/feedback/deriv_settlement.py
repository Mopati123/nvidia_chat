"""Closed-contract settlement and ML feedback for Deriv demo canaries."""

from __future__ import annotations

import csv
import glob
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from tachyonic_chain.audit_log import append_execution_evidence
from trading.feedback.demo_settlement import _build_ml_artifacts
from trading.feedback.falsification import append_falsification_evidence, score_decision

logger = logging.getLogger(__name__)


@dataclass
class DerivContractTrade:
    """A Deriv contract row emitted by the live demo runner."""

    contract_id: str
    symbol: str
    direction: str
    entry: float
    stop: float
    target: float
    size: float
    predicted_pnl: float
    source: str
    opened_at: str
    csv_path: str


@dataclass
class DerivSettlementRecord:
    """Settlement state for one Deriv contract."""

    contract_id: str
    status: str
    symbol: str
    source: str
    csv_path: str
    direction: str = ""
    size: float = 0.0
    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    predicted_pnl: float = 0.0
    contract_type: str = ""
    buy_price: Optional[float] = None
    sell_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    close_reason: Optional[str] = None
    closed_at: Optional[float] = None
    ppo_feedback_status: str = "not_attempted"
    falsification_status: str = "not_scored"
    falsification_hash: Optional[str] = None
    evidence_hash: Optional[str] = None


@dataclass
class DerivSettlementRunReport:
    """Summary for a Deriv settlement pass."""

    scanned: int
    closed: int
    open: int
    missing_history: int
    already_settled: int
    ledger_path: str
    records: List[DerivSettlementRecord] = field(default_factory=list)
    dataset_report: Optional[Dict[str, Any]] = None
    model_report: Optional[Dict[str, Any]] = None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _maybe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _contract_attr(contract: Any, name: str, default: Any = None) -> Any:
    if isinstance(contract, dict):
        return contract.get(name, default)
    return getattr(contract, name, default)


def _contract_id(contract: Any) -> Optional[str]:
    value = (
        _contract_attr(contract, "contract_id")
        or _contract_attr(contract, "id")
        or _contract_attr(contract, "transaction_id")
    )
    if value in (None, ""):
        return None
    return str(value)


def _is_numeric_id(value: Any) -> bool:
    try:
        int(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _is_closed_contract(contract: Any) -> bool:
    status = str(_contract_attr(contract, "status", "") or "").lower()
    if status in {"won", "lost", "sold", "closed"}:
        return True
    if status == "open":
        return False
    try:
        if int(_contract_attr(contract, "is_sold", 0) or 0) == 1:
            return True
    except (TypeError, ValueError):
        pass
    try:
        if int(_contract_attr(contract, "is_expired", 0) or 0) == 1:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _close_reason(contract: Any) -> str:
    status = str(_contract_attr(contract, "status", "") or "").lower()
    if status in {"won", "lost", "sold", "closed"}:
        return status
    try:
        if int(_contract_attr(contract, "is_sold", 0) or 0) == 1:
            return "sold"
    except (TypeError, ValueError):
        pass
    try:
        if int(_contract_attr(contract, "is_expired", 0) or 0) == 1:
            return "expired"
    except (TypeError, ValueError):
        pass
    return "unknown"


def _realized_pnl(contract: Any) -> Optional[float]:
    profit = _maybe_float(_contract_attr(contract, "profit"))
    if profit is not None:
        return round(profit, 4)

    sell_price = _maybe_float(
        _contract_attr(contract, "sell_price")
        or _contract_attr(contract, "bid_price")
    )
    buy_price = _maybe_float(_contract_attr(contract, "buy_price"))
    if sell_price is not None and buy_price is not None:
        return round(sell_price - buy_price, 4)
    return None


def load_deriv_contract_trades(patterns: Sequence[str | Path]) -> List[DerivContractTrade]:
    """Load Deriv live-demo contract rows from one or more demo trade CSV files."""
    paths: List[Path] = []
    for pattern in patterns:
        text = str(pattern)
        matches = glob.glob(text)
        paths.extend(Path(match) for match in matches) if matches else paths.append(Path(text))

    trades: Dict[str, DerivContractTrade] = {}
    for path in sorted({p for p in paths if p.exists()}):
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                source = str(row.get("source") or "").strip().lower()
                contract_id = str(row.get("ticket") or "").strip()
                if source != "deriv" or not _is_numeric_id(contract_id):
                    continue
                trades[contract_id] = DerivContractTrade(
                    contract_id=contract_id,
                    symbol=str(row.get("symbol") or ""),
                    direction=str(row.get("direction") or ""),
                    entry=_float(row.get("entry")),
                    stop=_float(row.get("stop")),
                    target=_float(row.get("target")),
                    size=_float(row.get("size")),
                    predicted_pnl=_float(row.get("predicted_pnl")),
                    source="deriv",
                    opened_at=str(row.get("time") or ""),
                    csv_path=str(path),
                )
    return list(trades.values())


def active_contract_id_set(contracts: Optional[Iterable[Any]]) -> Set[str]:
    """Return active Deriv contract IDs from portfolio output."""
    ids: Set[str] = set()
    for contract in contracts or []:
        contract_id = _contract_id(contract)
        if contract_id is not None:
            ids.add(contract_id)
    return ids


def read_settled_contract_ids(ledger_path: str | Path) -> Set[str]:
    """Read contract IDs already written to the Deriv settlement ledger."""
    path = Path(ledger_path)
    if not path.exists():
        return set()
    ids: Set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("status") == "closed" and record.get("contract_id"):
            ids.add(str(record["contract_id"]))
    return ids


def settle_deriv_contract(
    trade: DerivContractTrade,
    active_contract_ids: Set[str],
    contract_statuses: Dict[str, Any],
    profit_table: Iterable[Any],
) -> DerivSettlementRecord:
    """Classify one Deriv contract as open, closed, or missing from history."""
    base = DerivSettlementRecord(
        contract_id=trade.contract_id,
        status="open" if trade.contract_id in active_contract_ids else "missing_history",
        symbol=trade.symbol,
        source=trade.source,
        csv_path=trade.csv_path,
        direction=trade.direction,
        size=trade.size,
        entry=trade.entry,
        stop=trade.stop,
        target=trade.target,
        predicted_pnl=trade.predicted_pnl,
    )

    if trade.contract_id in active_contract_ids:
        return base

    status_contract = contract_statuses.get(trade.contract_id)
    if status_contract and not _is_closed_contract(status_contract):
        base.status = "open"
        return base

    profit_by_id = {
        contract_id: row
        for row in (profit_table or [])
        if (contract_id := _contract_id(row)) is not None
    }
    settled_contract = status_contract if status_contract and _is_closed_contract(status_contract) else None
    settled_contract = settled_contract or profit_by_id.get(trade.contract_id)
    if not settled_contract:
        return base

    realized = _realized_pnl(settled_contract)
    if realized is None:
        return base

    base.status = "closed"
    base.contract_type = str(_contract_attr(settled_contract, "contract_type", "") or "")
    base.buy_price = _maybe_float(_contract_attr(settled_contract, "buy_price"))
    base.sell_price = _maybe_float(
        _contract_attr(settled_contract, "sell_price")
        or _contract_attr(settled_contract, "bid_price")
    )
    base.realized_pnl = realized
    base.close_reason = _close_reason(settled_contract)
    base.closed_at = _maybe_float(
        _contract_attr(settled_contract, "exit_spot_time")
        or _contract_attr(settled_contract, "sell_time")
        or _contract_attr(settled_contract, "transaction_time")
    )
    return base


def append_deriv_settlement_record(record: DerivSettlementRecord, ledger_path: str | Path) -> None:
    """Append one closed Deriv contract settlement to the JSONL ledger."""
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True, separators=(",", ":"), default=str))
        handle.write("\n")


def append_deriv_settlement_evidence(record: DerivSettlementRecord, evidence_log_path: str | Path) -> str:
    """Append closed Deriv settlement evidence to the hash-chained audit log."""
    return append_execution_evidence(
        event_type="deriv_contract_settlement",
        execution_id=f"settled_deriv_{record.contract_id}",
        operation="live_demo_settlement",
        symbol=record.symbol,
        outcome="success",
        token_status="deriv_history_verified",
        payload={
            "broker": "deriv",
            "contract_id": record.contract_id,
            "contract_type": record.contract_type,
            "direction": record.direction,
            "amount": record.buy_price,
            "entry": record.entry,
            "stop": record.stop,
            "target": record.target,
            "predicted_pnl": record.predicted_pnl,
            "realized_pnl": record.realized_pnl,
            "close_reason": record.close_reason,
            "ppo_feedback_status": record.ppo_feedback_status,
        },
        log_path=evidence_log_path,
    )


def _load_ppo_hook(checkpoint_path: Path, pending_path: Path):
    from trading.rl.ppo_paper_hook import PPOPaperHook
    from trading.rl.scheduler_agent import PPOSchedulerAgent

    agent = PPOSchedulerAgent()
    if checkpoint_path.exists():
        agent.load(str(checkpoint_path))
    hook = PPOPaperHook(agent)
    if pending_path.exists():
        pending_text = pending_path.read_text(encoding="utf-8")
        if pending_text.strip():
            try:
                pending_data = json.loads(pending_text)
                hook.import_pending(pending_data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse pending data from {pending_path}: {e}. Content: {pending_text[:200]}")
        else:
            logger.warning(f"Pending file {pending_path} is empty")
    return hook


def _save_ppo_hook(hook: Any, checkpoint_path: Path, pending_path: Path) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    hook.agent.save(str(checkpoint_path))
    pending_path.write_text(json.dumps(hook.export_pending(), indent=2, sort_keys=True), encoding="utf-8")


def feed_deriv_settlement_to_ppo(record: DerivSettlementRecord, checkpoint_path: str | Path,
                                 pending_path: str | Path) -> str:
    """Feed one closed Deriv settlement into PPO if matching pending state exists."""
    checkpoint_path = Path(checkpoint_path)
    pending_path = Path(pending_path)
    if record.status != "closed":
        return "not_closed"
    if record.realized_pnl is None:
        return "missing_realized_pnl"
    if not pending_path.exists():
        return "missing_pending_state"

    try:
        hook = _load_ppo_hook(checkpoint_path, pending_path)
        if not hook.has_pending(record.contract_id):
            return "missing_pending_state"
        before_updates = hook.agent.n_updates
        stored = hook.on_trade_closed(record.contract_id, record.realized_pnl)
        if not stored:
            return "missing_pending_state"
        _save_ppo_hook(hook, checkpoint_path, pending_path)
        return "updated" if hook.agent.n_updates > before_updates else "transition_stored"
    except Exception as exc:
        return f"ppo_error:{type(exc).__name__}"


def _query_deriv(contract_ids: Iterable[str], broker: Optional[Any] = None,
                 profit_limit: int = 500) -> tuple[List[Any], Dict[str, Any], List[Any]]:
    created = False
    if broker is None:
        from trading.brokers.deriv_broker import DerivBroker

        broker = DerivBroker()
        if not broker.connect() or not getattr(broker, "authorized", False):
            raise RuntimeError("Deriv authorization failed")
        created = True

    try:
        active_contracts = list(broker.get_active_contracts() or [])
        statuses = {
            contract_id: status
            for contract_id in contract_ids
            if (status := broker.get_contract_status(contract_id)) is not None
        }
        profit_rows = list(broker.get_profit_table(limit=profit_limit) or [])
        return active_contracts, statuses, profit_rows
    finally:
        if created:
            broker.disconnect()


def settle_deriv_contracts(
    *,
    trade_patterns: Sequence[str | Path] = ("logs/demo_trades_*.csv",),
    ledger_path: str | Path = "logs/deriv_contract_settlements.jsonl",
    evidence_log_path: str | Path = "logs/execution_evidence.jsonl",
    ppo_checkpoint_path: str | Path = "data/models/ppo_live_demo.pt",
    ppo_pending_path: str | Path = "data/models/ppo_live_demo_pending.json",
    dataset_path: str | Path = "data/evidence_dataset/refusal_risk.parquet",
    model_path: str | Path = "data/models/refusal_risk_model.json",
    active_contracts: Optional[Iterable[Any]] = None,
    contract_statuses: Optional[Dict[str, Any]] = None,
    profit_table: Optional[Iterable[Any]] = None,
    broker: Optional[Any] = None,
    profit_limit: int = 500,
    rebuild_ml: bool = True,
) -> DerivSettlementRunReport:
    """Settle closed Deriv demo contracts and feed closed outcomes into ML artifacts."""
    trades = load_deriv_contract_trades(trade_patterns)
    if not trades:
        return DerivSettlementRunReport(
            scanned=0,
            closed=0,
            open=0,
            missing_history=0,
            already_settled=0,
            ledger_path=str(ledger_path),
            records=[],
        )

    if active_contracts is None or contract_statuses is None or profit_table is None:
        active_contracts, contract_statuses, profit_table = _query_deriv(
            [trade.contract_id for trade in trades],
            broker=broker,
            profit_limit=profit_limit,
        )

    active_ids = active_contract_id_set(active_contracts)
    existing = read_settled_contract_ids(ledger_path)
    records: List[DerivSettlementRecord] = []
    already_settled = 0
    new_closed = 0

    for trade in trades:
        record = settle_deriv_contract(trade, active_ids, contract_statuses or {}, profit_table or [])
        if record.status == "closed":
            if record.contract_id in existing:
                already_settled += 1
                record.ppo_feedback_status = "already_settled"
            else:
                record.ppo_feedback_status = feed_deriv_settlement_to_ppo(
                    record,
                    ppo_checkpoint_path,
                    ppo_pending_path,
                )
                record.evidence_hash = append_deriv_settlement_evidence(record, evidence_log_path)
                falsification = score_decision(
                    "AUTHORIZED",
                    realized_pnl=record.realized_pnl,
                    predicted_pnl=record.predicted_pnl,
                    symbol=record.symbol,
                    broker="deriv",
                    reference_id=record.contract_id,
                    metadata={
                        "close_reason": record.close_reason,
                        "contract_type": record.contract_type,
                        "source": record.source,
                    },
                )
                record.falsification_status = falsification.classification
                record.falsification_hash = append_falsification_evidence(
                    falsification,
                    evidence_log_path,
                )
                append_deriv_settlement_record(record, ledger_path)
                existing.add(record.contract_id)
                new_closed += 1
        records.append(record)

    dataset_report = None
    model_report = None
    if rebuild_ml and new_closed > 0:
        dataset_report, model_report = _build_ml_artifacts(evidence_log_path, dataset_path, model_path)

    return DerivSettlementRunReport(
        scanned=len(records),
        closed=sum(1 for record in records if record.status == "closed"),
        open=sum(1 for record in records if record.status == "open"),
        missing_history=sum(1 for record in records if record.status == "missing_history"),
        already_settled=already_settled,
        ledger_path=str(ledger_path),
        records=records,
        dataset_report=dataset_report,
        model_report=model_report,
    )
