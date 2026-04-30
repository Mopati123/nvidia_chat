#!/usr/bin/env python3
"""Train the offline refusal/risk baseline model from a sanitized dataset."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_core.ml.refusal_risk_trainer import train_refusal_risk_model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/evidence_dataset/refusal_risk.parquet", help="Input Parquet dataset")
    parser.add_argument("--output", default="data/models/refusal_risk_model.json", help="Output model artifact")
    parser.add_argument("--seed", type=int, default=12345, help="Deterministic training seed")
    args = parser.parse_args()

    report = train_refusal_risk_model(args.dataset, args.output, seed=args.seed)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
