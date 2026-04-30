#!/usr/bin/env python3
"""Build a sanitized refusal/risk dataset from execution evidence logs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_core.ml.evidence_dataset import build_refusal_risk_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="logs/execution_evidence.jsonl", help="Input JSONL audit log")
    parser.add_argument("--output", default="data/evidence_dataset/refusal_risk.parquet", help="Output Parquet dataset")
    args = parser.parse_args()

    report = build_refusal_risk_dataset(args.input, args.output)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

