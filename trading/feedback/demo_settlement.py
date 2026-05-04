"""Closed-trade settlement and ML feedback for MT5 demo forward tests."""

from __future__ import annotations

import csv
import glob
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from tachyonic_chain.audit_log import append_execution_evidence


CLOSE_ENTRY = 1
REASON_MAP = {
    0: "manual",
    3: "manual",
    4: "sl",
    5: "tp",
}


@dataclass
class DemoTrade:
    """A broker-ticket trade row emitted by the live demo runner."""

    ticket: str
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
class SettlementRecord:
    """Settlement state for one demo trade ticket."""

    ticket: str
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
    realized_pnl: Optional[float] = None
    close_reason: Optional[str] = None
    closed_at: Optional[float] = None
    ppo_feedback_status: str = "not_attempted"
    evidence_hash: Optional[str] = None


@dataclass
class SettlementRunReport:
    """Summary for a settlement pass."""

    scanned: int
    closed: int
    open: int
    missing_history: int
    already_settled: int
    ledger_path: str
    records: List[SettlementRecord] = field(default_factory=list)
    dataset_report: Optional[Dict[str, Any]] = None
    model_report: Optional[Dict[str, Any]] = None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _deal_attr(deal: Any, name: str, default: Any = None) -> Any:
    if isinstance(deal, dict):
        return deal.get(name, default)
    return getattr(deal, name, default)


def _position_ticket(position: Any) -> Optional[int]:
    value = _deal_attr(position, "ticket")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_numeric_ticket(ticket: Any) -> bool:
    try:
        int(str(ticket))
        return True
    except (TypeError, ValueError):
        return False


def classify_close_reason(deal: Any) -> str:
    """Map an MT5 closing deal reason into a stable audit label."""
    try:
        reason = int(_deal_attr(deal, "reason", -1))
    except (TypeError, ValueError):
        reason = -1
    return REASON_MAP.get(reason, f"reason_{reason}" if reason >= 0 else "unknown")


def load_demo_trades(patterns: Sequence[str | Path]) -> List[DemoTrade]:
    """Load numeric MT5 tickets from one or more demo trade CSV files."""
    paths: List[Path] = []
    for pattern in patterns:
        text = str(pattern)
        matches = glob.glob(text)
        paths.extend(Path(match) for match in matches) if matches else paths.append(Path(text))

    trades: Dict[str, DemoTrade] = {}
    for path in sorted({p for p in paths if p.exists()}):
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                ticket = str(row.get("ticket") or "").strip()
                if not _is_numeric_ticket(ticket):
                    continue
                source = str(row.get("source") or "").strip().lower()
                if source and source != "mt5":
                    continue
                trades[ticket] = DemoTrade(
                    ticket=ticket,
                    symbol=str(row.get("symbol") or ""),
                    direction=str(row.get("direction") or ""),
                    entry=_float(row.get("entry")),
                    stop=_float(row.get("stop")),
                    target=_float(row.get("target")),
                    size=_float(row.get("size")),
                    predicted_pnl=_float(row.get("predicted_pnl")),
                    source=source or "mt5",
                    opened_at=str(row.get("time") or ""),
                    csv_path=str(path),
                )
    return list(trades.values())


def open_ticket_set(positions: Optional[Iterable[Any]]) -> Set[int]:
    """Return open position tickets from MT5 positions_get output."""
    tickets: Set[int] = set()
    for position in positions or []:
        ticket = _position_ticket(position)
        if ticket is not None:
            tickets.add(ticket)
    return tickets


def settle_trade(trade: DemoTrade, open_tickets: Set[int], history_deals: Iterable[Any]) -> SettlementRecord:
    """Classify one trade as open, closed, or missing from MT5 history."""
    ticket_int = int(trade.ticket)
    base = SettlementRecord(
        ticket=trade.ticket,
        status="open" if ticket_int in open_tickets else "missing_history",
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

    if ticket_int in open_tickets:
        return base

    closing_deals = [
        deal for deal in history_deals
        if int(_deal_attr(deal, "position_id", -1) or -1) == ticket_int
        and int(_deal_attr(deal, "entry", -1) or -1) == CLOSE_ENTRY
    ]
    if not closing_deals:
        return base

    lifecycle_deals = [
        deal for deal in history_deals
        if int(_deal_attr(deal, "position_id", -1) or -1) == ticket_int
    ]
    closing_deals.sort(key=lambda deal: float(_deal_attr(deal, "time", 0) or 0))
    realized = 0.0
    for deal in lifecycle_deals:
        realized += _float(_deal_attr(deal, "profit"))
        realized += _float(_deal_attr(deal, "swap"))
        realized += _float(_deal_attr(deal, "commission"))

    last = closing_deals[-1]
    base.status = "closed"
    base.realized_pnl = round(realized, 4)
    base.close_reason = classify_close_reason(last)
    base.closed_at = _float(_deal_attr(last, "time"), 0.0)
    return base


def read_settled_tickets(ledger_path: str | Path) -> Set[str]:
    """Read tickets already written to the settlement ledger."""
    path = Path(ledger_path)
    if not path.exists():
        return set()
    tickets: Set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("status") == "closed" and record.get("ticket"):
            tickets.add(str(record["ticket"]))
    return tickets


def append_settlement_record(record: SettlementRecord, ledger_path: str | Path) -> None:
    """Append one closed settlement to the JSONL ledger."""
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True, separators=(",", ":"), default=str))
        handle.write("\n")


def append_settlement_evidence(record: SettlementRecord, evidence_log_path: str | Path) -> str:
    """Append closed-trade settlement evidence to the hash-chained audit log."""
    return append_execution_evidence(
        event_type="demo_trade_settlement",
        execution_id=f"settled_mt5_{record.ticket}",
        operation="live_demo_settlement",
        symbol=record.symbol,
        outcome="success",
        token_status="mt5_history_verified",
        payload={
            "broker": "mt5",
            "ticket": record.ticket,
            "direction": record.direction,
            "volume": record.size,
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
        hook.import_pending(json.loads(pending_path.read_text(encoding="utf-8")))
    return hook


def _save_ppo_hook(hook: Any, checkpoint_path: Path, pending_path: Path) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    hook.agent.save(str(checkpoint_path))
    pending_path.write_text(json.dumps(hook.export_pending(), indent=2, sort_keys=True), encoding="utf-8")


def feed_settlement_to_ppo(record: SettlementRecord, checkpoint_path: str | Path,
                           pending_path: str | Path) -> str:
    """Feed one closed settlement into PPO if matching pending state exists."""
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
        if not hook.has_pending(record.ticket):
            return "missing_pending_state"
        before_updates = hook.agent.n_updates
        stored = hook.on_trade_closed(record.ticket, record.realized_pnl)
        if not stored:
            return "missing_pending_state"
        _save_ppo_hook(hook, checkpoint_path, pending_path)
        return "updated" if hook.agent.n_updates > before_updates else "transition_stored"
    except Exception as exc:
        return f"ppo_error:{type(exc).__name__}"


def _query_mt5(days: int) -> tuple[List[Any], List[Any]]:
    import MetaTrader5 as mt5

    if not mt5.initialize(
        login=int(os.environ["MT5_ACCOUNT_ID"]),
        password=os.environ["MT5_PASSWORD"],
        server=os.environ["MT5_SERVER"],
        timeout=10000,
    ):
        raise RuntimeError(f"mt5.initialize failed: {mt5.last_error()}")
    try:
        positions = list(mt5.positions_get() or [])
        date_from = datetime.now(timezone.utc) - timedelta(days=days)
        date_to = datetime.now(timezone.utc) + timedelta(days=1)
        deals = list(mt5.history_deals_get(date_from, date_to) or [])
        return positions, deals
    finally:
        mt5.shutdown()


def _build_ml_artifacts(evidence_log_path: str | Path, dataset_path: str | Path,
                        model_path: str | Path) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    from data_core.ml.evidence_dataset import build_refusal_risk_dataset
    from data_core.ml.refusal_risk_trainer import train_refusal_risk_model

    dataset_report = build_refusal_risk_dataset(evidence_log_path, dataset_path)
    model_report = None
    if dataset_report.valid and dataset_report.rows > 0:
        model_report = train_refusal_risk_model(dataset_path, model_path)
    return asdict(dataset_report), asdict(model_report) if model_report else None


def settle_demo_trades(
    *,
    trade_patterns: Sequence[str | Path] = ("logs/demo_trades_*.csv",),
    ledger_path: str | Path = "logs/demo_trade_settlements.jsonl",
    evidence_log_path: str | Path = "logs/execution_evidence.jsonl",
    ppo_checkpoint_path: str | Path = "data/models/ppo_live_demo.pt",
    ppo_pending_path: str | Path = "data/models/ppo_live_demo_pending.json",
    dataset_path: str | Path = "data/evidence_dataset/refusal_risk.parquet",
    model_path: str | Path = "data/models/refusal_risk_model.json",
    positions: Optional[Iterable[Any]] = None,
    history_deals: Optional[Iterable[Any]] = None,
    mt5_history_days: int = 7,
    rebuild_ml: bool = True,
) -> SettlementRunReport:
    """Settle closed MT5 demo trades and feed closed outcomes into ML artifacts."""
    if positions is None or history_deals is None:
        positions, history_deals = _query_mt5(mt5_history_days)

    trades = load_demo_trades(trade_patterns)
    open_tickets = open_ticket_set(positions)
    existing = read_settled_tickets(ledger_path)
    records: List[SettlementRecord] = []
    already_settled = 0
    new_closed = 0

    for trade in trades:
        record = settle_trade(trade, open_tickets, history_deals or [])
        if record.status == "closed":
            if record.ticket in existing:
                already_settled += 1
                record.ppo_feedback_status = "already_settled"
            else:
                record.ppo_feedback_status = feed_settlement_to_ppo(
                    record,
                    ppo_checkpoint_path,
                    ppo_pending_path,
                )
                record.evidence_hash = append_settlement_evidence(record, evidence_log_path)
                append_settlement_record(record, ledger_path)
                existing.add(record.ticket)
                new_closed += 1
        records.append(record)

    dataset_report = None
    model_report = None
    if rebuild_ml and new_closed > 0:
        dataset_report, model_report = _build_ml_artifacts(evidence_log_path, dataset_path, model_path)

    return SettlementRunReport(
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
