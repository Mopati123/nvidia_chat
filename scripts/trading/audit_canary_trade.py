"""Read-only audit for MT5 live-demo canary executions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from trading.brokers.credentials import resolve_mt5_credentials


DONE_RETCODE = 10009
AUDIT_MARKER_RE = re.compile(r"CANARY_AUDIT\s+gate=(?P<gate>\S+)\s+status=(?P<status>\S+)(?P<fields>.*)")


@dataclass
class GateCheck:
    name: str
    status: str
    evidence: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanaryAuditReport:
    ticket: str
    classification: str
    execution_path_passed: bool
    learning_flagged: bool
    blockers: List[str]
    gates: List[GateCheck]
    artifacts: Dict[str, Any]
    mt5_position: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket": self.ticket,
            "classification": self.classification,
            "execution_path_passed": self.execution_path_passed,
            "learning_flagged": self.learning_flagged,
            "blockers": self.blockers,
            "gates": [gate.__dict__ for gate in self.gates],
            "artifacts": self.artifacts,
            "mt5_position": self.mt5_position,
        }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _read_trade_csv(path: Path, ticket: str) -> Optional[Dict[str, str]]:
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("ticket", "")) == str(ticket):
                return dict(row)
    return None


def _iter_evidence(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"_decode_error": line[:120]})
    return records


def _find_ticket_evidence(path: Path, ticket: str) -> Optional[Dict[str, Any]]:
    expected_id = f"mt5_{ticket}"
    for record in _iter_evidence(path):
        payload = record.get("payload") or {}
        if record.get("execution_id") == expected_id:
            return record
        if str(payload.get("ticket", "")) == str(ticket):
            return record
    return None


def _verify_evidence_chain(path: Path) -> Optional[bool]:
    if not path.exists():
        return None
    try:
        from tachyonic_chain.audit_log import verify_execution_evidence_chain

        return bool(verify_execution_evidence_chain(path).valid)
    except Exception:
        return None


def _parse_audit_markers(log_text: str) -> Dict[str, List[Dict[str, Any]]]:
    markers: Dict[str, List[Dict[str, Any]]] = {}
    for line in log_text.splitlines():
        match = AUDIT_MARKER_RE.search(line)
        if not match:
            continue
        fields: Dict[str, str] = {}
        for token in match.group("fields").strip().split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            fields[key] = value
        markers.setdefault(match.group("gate"), []).append({
            "status": match.group("status"),
            "fields": fields,
            "line": line,
        })
    return markers


def _marker_status(markers: Dict[str, List[Dict[str, Any]]], gate: str) -> Optional[str]:
    entries = markers.get(gate) or []
    return entries[-1]["status"] if entries else None


def _gate(name: str, status: str, evidence: str, **details: Any) -> GateCheck:
    return GateCheck(name=name, status=status, evidence=evidence, details={k: v for k, v in details.items() if v is not None})


def _query_mt5_position(ticket: str) -> Dict[str, Any]:
    account, password, server = resolve_mt5_credentials()
    if not (account and password and server):
        return {"checked": False, "error": "MT5 credentials unavailable from env or secure store"}

    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        return {"checked": False, "error": f"MetaTrader5 import failed: {type(exc).__name__}: {exc}"}

    result: Dict[str, Any] = {"checked": False, "open_positions_total": None, "matching_position": None}
    try:
        if not mt5.initialize(
            login=int(account),
            password=password,
            server=server,
            timeout=10000,
        ):
            result["error"] = f"mt5.initialize failed: {mt5.last_error()}"
            return result
        positions = mt5.positions_get()
        if positions is None:
            result["error"] = f"positions_get failed: {mt5.last_error()}"
            return result
        result["checked"] = True
        result["open_positions_total"] = len(positions)
        for position in positions:
            data = position._asdict()
            if str(data.get("ticket")) == str(ticket):
                result["matching_position"] = {
                    "ticket": data.get("ticket"),
                    "symbol": data.get("symbol"),
                    "type": data.get("type"),
                    "volume": data.get("volume"),
                    "price_open": data.get("price_open"),
                    "sl": data.get("sl"),
                    "tp": data.get("tp"),
                    "profit": data.get("profit"),
                }
                break
        return result
    finally:
        mt5.shutdown()


def audit_canary_trade(
    ticket: str,
    live_log_path: Path,
    trade_csv_path: Path,
    evidence_log_path: Path,
    *,
    check_mt5: bool = False,
) -> CanaryAuditReport:
    log_text = _read_text(live_log_path)
    markers = _parse_audit_markers(log_text)
    csv_row = _read_trade_csv(trade_csv_path, ticket)
    evidence = _find_ticket_evidence(evidence_log_path, ticket)
    payload = evidence.get("payload", {}) if evidence else {}
    mt5_position = _query_mt5_position(ticket) if check_mt5 else None

    gates: List[GateCheck] = []
    blockers: List[str] = []

    live_demo_ok = (
        "MT5 demo connected" in log_text
        and "Pipeline paper_mode=False" in log_text
        and csv_row is not None
        and csv_row.get("source") == "mt5"
        and payload.get("broker") == "mt5"
    )
    gates.append(_gate(
        "mt5_live_demo_routing",
        "passed" if live_demo_ok else "failed",
        "MT5 demo connection, live-demo mode, CSV source, and broker evidence agree",
        csv_source=csv_row.get("source") if csv_row else None,
        broker=payload.get("broker"),
    ))
    if not live_demo_ok:
        blockers.append("MT5 live-demo routing evidence is incomplete")

    stage12_status = _marker_status(markers, "stage12_admissibility")
    if stage12_status:
        gates.append(_gate("stage12_admissibility", stage12_status, "explicit CANARY_AUDIT marker found"))
    elif evidence and payload.get("retcode") == DONE_RETCODE:
        gates.append(_gate(
            "stage12_admissibility",
            "inferred",
            "Stage 16 broker success requires prior risk/admissibility passage in the orchestrator",
        ))
    else:
        gates.append(_gate("stage12_admissibility", "missing", "no explicit or inferable admissibility evidence"))
        blockers.append("Stage 12 admissibility evidence missing")

    stage15_status = _marker_status(markers, "stage15_scheduler")
    if stage15_status:
        gates.append(_gate("stage15_scheduler", stage15_status, "explicit CANARY_AUDIT marker found"))
    elif evidence and evidence.get("token_status") == "authorized":
        gates.append(_gate(
            "stage15_scheduler",
            "inferred",
            "broker evidence has token_status=authorized for live_execution",
        ))
    else:
        gates.append(_gate("stage15_scheduler", "missing", "no scheduler authorization evidence"))
        blockers.append("Stage 15 scheduler authorization evidence missing")

    token_ok = evidence is not None and evidence.get("token_status") == "authorized"
    gates.append(_gate(
        "broker_token_validator",
        "passed" if token_ok else "failed",
        "broker execution evidence token_status",
        token_status=evidence.get("token_status") if evidence else None,
    ))
    if not token_ok:
        blockers.append("broker token validator did not report authorized")

    retcode_ok = payload.get("retcode") == DONE_RETCODE and evidence.get("outcome") == "success" if evidence else False
    gates.append(_gate(
        "mt5_broker_execution",
        "passed" if retcode_ok else "failed",
        "MT5 evidence outcome and retcode",
        outcome=evidence.get("outcome") if evidence else None,
        retcode=payload.get("retcode"),
    ))
    if not retcode_ok:
        blockers.append(f"MT5 execution retcode/outcome not successful for ticket {ticket}")

    artifact_ok = bool(csv_row and evidence and str(payload.get("ticket")) == str(ticket))
    gates.append(_gate(
        "artifact_consistency",
        "passed" if artifact_ok else "failed",
        "CSV ticket and broker evidence match; MT5 position check is informational after close",
        csv_ticket=csv_row.get("ticket") if csv_row else None,
        evidence_ticket=payload.get("ticket"),
        mt5_checked=mt5_position.get("checked") if mt5_position else False,
        mt5_open_positions=mt5_position.get("open_positions_total") if mt5_position else None,
        mt5_matching_position=bool(mt5_position.get("matching_position")) if mt5_position else None,
    ))
    if not artifact_ok:
        blockers.append(f"artifact mismatch for ticket {ticket}")

    chain_valid = _verify_evidence_chain(evidence_log_path)
    if chain_valid is not None:
        gates.append(_gate(
            "evidence_chain",
            "passed" if chain_valid else "failed",
            "execution evidence hash chain verification",
        ))
        if not chain_valid:
            blockers.append("execution evidence hash chain is invalid")

    reconciliation_status = _marker_status(markers, "stage17_reconciliation")
    learning_status = _marker_status(markers, "stage19_weight_update")
    learning_flagged = (
        reconciliation_status == "flagged"
        or learning_status == "flagged"
        or "PnL divergence" in log_text
        or "Weight update blocked" in log_text
    )
    gates.append(_gate(
        "stage17_reconciliation",
        "flagged" if learning_flagged else "passed",
        "reconciliation and learning warnings in live log",
        pnl_divergence_logged="PnL divergence" in log_text,
        weight_block_logged="Weight update blocked" in log_text,
    ))

    execution_path_passed = not blockers
    if execution_path_passed and learning_flagged:
        classification = "EXECUTION_PATH_PASSED_LEARNING_FLAGGED"
    elif execution_path_passed:
        classification = "EXECUTION_PATH_PASSED"
    else:
        classification = "BLOCKED"

    return CanaryAuditReport(
        ticket=str(ticket),
        classification=classification,
        execution_path_passed=execution_path_passed,
        learning_flagged=learning_flagged,
        blockers=blockers,
        gates=gates,
        artifacts={
            "live_log": str(live_log_path),
            "trade_csv": str(trade_csv_path),
            "evidence_log": str(evidence_log_path),
            "csv_row": csv_row,
            "evidence_record": evidence,
        },
        mt5_position=mt5_position,
    )


def print_human(report: CanaryAuditReport) -> None:
    print(f"ticket: {report.ticket}")
    print(f"classification: {report.classification}")
    print(f"execution_path_passed: {str(report.execution_path_passed).lower()}")
    print(f"learning_flagged: {str(report.learning_flagged).lower()}")
    if report.blockers:
        print("blockers:")
        for blocker in report.blockers:
            print(f"- {blocker}")
    print("gates:")
    for gate in report.gates:
        print(f"- {gate.name}: {gate.status} ({gate.evidence})")
    if report.mt5_position:
        print(f"mt5_position: {json.dumps(report.mt5_position, sort_keys=True)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit an MT5 live-demo canary trade without placing orders.")
    parser.add_argument("--ticket", required=True, help="MT5 broker ticket to audit")
    parser.add_argument("--live-log", required=True, type=Path, help="live_canary stderr/stdout log path")
    parser.add_argument("--trade-csv", required=True, type=Path, help="demo_trades CSV path")
    parser.add_argument("--evidence-log", required=True, type=Path, help="execution_evidence JSONL path")
    parser.add_argument("--check-mt5", action="store_true", help="read current MT5 positions and match the ticket")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of human text")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit_canary_trade(
        args.ticket,
        args.live_log,
        args.trade_csv,
        args.evidence_log,
        check_mt5=args.check_mt5,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0 if report.execution_path_passed else 2


if __name__ == "__main__":
    sys.exit(main())
