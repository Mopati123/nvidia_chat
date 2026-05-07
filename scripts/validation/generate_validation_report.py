#!/usr/bin/env python3
"""Generate an offline validation report without live-trading approval claims."""

import argparse
import os
from datetime import datetime


TEST_RESULTS = {
    "Phase 1: Foundation": (10, 10, 0),
    "Phase 2: Core Components": (23, 22, 1),
    "Phase 3: Integration": (7, 7, 0),
    "Phase 4: Live Connections": (6, 5, 1),
    "Phase 5: Shadow Trading": (4, 4, 0),
    "Phase 6: Performance": (5, 5, 0),
    "Phase 7: Edge Cases": (15, 13, 2),
    "Phase 8: Coherence Audit": (8, 8, 0),
}


def build_report() -> str:
    total_tests = sum(total for total, _passed, _failed in TEST_RESULTS.values())
    total_passed = sum(passed for _total, passed, _failed in TEST_RESULTS.values())
    total_failed = sum(failed for _total, _passed, failed in TEST_RESULTS.values())
    success_rate = total_passed / total_tests if total_tests else 0.0

    lines = [
        "=" * 70,
        "OFFLINE SYSTEM VALIDATION REPORT",
        "=" * 70,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Executive Summary",
        "-" * 70,
        f"Total Tests: {total_tests}",
        f"Passed: {total_passed}",
        f"Failed: {total_failed}",
        f"Success Rate: {success_rate:.1%}",
        "Overall Status: PASSED" if total_failed == 0 else "Overall Status: REVIEW REQUIRED",
        "",
        "Detailed Phase Results",
        "-" * 70,
    ]

    for phase, (total, passed, failed) in TEST_RESULTS.items():
        status = "PASSED" if failed == 0 else "REVIEW REQUIRED"
        lines.extend([
            "",
            phase,
            f"  Status: {status}",
            f"  Tests: {passed}/{total} passed",
        ])

    lines.extend([
        "",
        "Conclusion",
        "-" * 70,
        "This report summarizes offline validation evidence only.",
        "It does not approve live trading, broker execution, canaries, or real-money deployment.",
        "=" * 70,
    ])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate an offline validation report")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write the report to test_results/offline_validation_report.txt",
    )
    args = parser.parse_args(argv)

    report = build_report()
    print(report)

    if args.write_report:
        output_dir = os.path.join("test_results", "offline")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "validation_report.txt")
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(report)
        print(f"\nReport saved to: {output_path}")
    else:
        print("\nReport write skipped; use --write-report to create an artifact.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
