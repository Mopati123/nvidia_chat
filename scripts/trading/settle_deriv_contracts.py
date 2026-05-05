"""Settle closed Deriv demo contracts and refresh offline ML feedback artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from trading.feedback.deriv_settlement import settle_deriv_contracts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trade-csv",
        action="append",
        dest="trade_csv",
        default=None,
        help="Trade CSV path or glob. May be repeated. Default: logs/demo_trades_*.csv",
    )
    parser.add_argument("--ledger", default="logs/deriv_contract_settlements.jsonl")
    parser.add_argument("--evidence-log", default="logs/execution_evidence.jsonl")
    parser.add_argument("--ppo-checkpoint", default="data/models/ppo_live_demo.pt")
    parser.add_argument("--ppo-pending", default="data/models/ppo_live_demo_pending.json")
    parser.add_argument("--dataset", default="data/evidence_dataset/refusal_risk.parquet")
    parser.add_argument("--model", default="data/models/refusal_risk_model.json")
    parser.add_argument("--profit-limit", type=int, default=500)
    parser.add_argument("--skip-ml-rebuild", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = settle_deriv_contracts(
        trade_patterns=args.trade_csv or ["logs/demo_trades_*.csv"],
        ledger_path=Path(args.ledger),
        evidence_log_path=Path(args.evidence_log),
        ppo_checkpoint_path=Path(args.ppo_checkpoint),
        ppo_pending_path=Path(args.ppo_pending),
        dataset_path=Path(args.dataset),
        model_path=Path(args.model),
        profit_limit=args.profit_limit,
        rebuild_ml=not args.skip_ml_rebuild,
    )

    payload = asdict(report)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"scanned: {report.scanned}")
        print(f"closed: {report.closed}")
        print(f"open: {report.open}")
        print(f"missing_history: {report.missing_history}")
        print(f"already_settled: {report.already_settled}")
        print(f"ledger: {report.ledger_path}")
        for record in report.records:
            print(
                f"- contract={record.contract_id} status={record.status} "
                f"realized={record.realized_pnl} reason={record.close_reason} "
                f"ppo={record.ppo_feedback_status}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
