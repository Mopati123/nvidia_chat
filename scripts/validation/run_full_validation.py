"""
Offline-safe validation runner.

Runs the legacy validation battery without broker/network tests by default and
without writing report artifacts unless explicitly requested.
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


TEST_CATEGORIES = {
    "Phase 1: Smoke Tests (Fast)": [
        ("scripts/validation/preflight_check.py", 30),
        ("validation/legacy/test_production_system.py", 60),
    ],
    "Phase 2: Core Feature Tests": [
        ("validation/legacy/test_taep_integration.py", 30),
        ("validation/legacy/test_riemannian_geometry.py", 30),
        ("validation/legacy/test_microstructure_integration.py", 30),
        ("validation/legacy/test_nn_integration.py", 30),
        ("validation/legacy/test_rl_integration.py", 30),
        ("validation/legacy/test_memory_integration.py", 30),
    ],
    "Phase 3: System Integration Tests": [
        ("validation/legacy/test_complete_system_e2e.py", 120),
        ("validation/legacy/test_full_system.py", 60),
        ("validation/legacy/test_integration.py", 30),
        ("validation/legacy/test_integration_final.py", 30),
    ],
    "Phase 4: Infrastructure & Broker Tests": [
        ("validation/legacy/test_deriv_connection.py", 30),
        ("validation/legacy/test_shadow_live.py", 30),
        ("validation/legacy/test_multi_agent.py", 30),
    ],
    "Phase 5: Specialized Tests": [
        ("validation/legacy/test_superposition.py", 30),
        ("validation/legacy/test_strategy_agent.py", 30),
        ("validation/legacy/test_acceleration.py", 30),
        ("validation/legacy/test_coherence_audit.py", 30),
    ],
}


def _command_for(test_file: str, allow_broker_network: bool) -> list[str]:
    command = [sys.executable, test_file]
    if test_file == "scripts/validation/preflight_check.py" and allow_broker_network:
        command.append("--allow-broker-network")
    return command


def run_test(test_file: str, timeout: int, allow_broker_network: bool = False) -> dict:
    """Run a single validation file and return a compact result."""
    start = time.time()
    try:
        result = subprocess.run(
            _command_for(test_file, allow_broker_network),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        elapsed = time.time() - start
        output = result.stdout + result.stderr
        return {
            "file": test_file,
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "elapsed": elapsed,
            "passed_count": output.count("[PASS]") + output.count("PASS:"),
            "failed_count": output.count("[FAIL]") + output.count("FAILED"),
            "output": output[-2000:] if len(output) > 2000 else output,
        }
    except subprocess.TimeoutExpired:
        return {
            "file": test_file,
            "passed": False,
            "error": "Timeout",
            "elapsed": timeout,
            "passed_count": 0,
            "failed_count": 0,
            "output": "Test timed out",
        }
    except Exception as exc:
        return {
            "file": test_file,
            "passed": False,
            "error": str(exc),
            "elapsed": 0,
            "passed_count": 0,
            "failed_count": 0,
            "output": str(exc),
        }


def print_results(results: list, category: str) -> tuple[int, int]:
    """Print test results for one category."""
    print(f"\n{'=' * 70}")
    print(category)
    print("=" * 70)
    passed = 0
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['file']:<40} ({result['elapsed']:.1f}s)")
        if result["passed"]:
            passed += 1
        elif "error" in result:
            print(f"     Error: {result['error']}")
        elif result.get("failed_count", 0) > 0:
            print(f"     Failed tests: {result['failed_count']}")
    print(f"\nCategory: {passed}/{len(results)} files passed")
    return passed, len(results)


def generate_certificate(all_results: list, total_time: float) -> str:
    """Generate an offline validation summary. This is not live approval."""
    total_files = len(all_results)
    passed_files = sum(1 for result in all_results if result["passed"])
    pass_rate = (passed_files / total_files * 100) if total_files else 0.0
    status = "OFFLINE CHECKS PASSED" if pass_rate == 100 else "REVIEW REQUIRED"
    return f"""
======================================================================
OFFLINE VALIDATION SUMMARY
======================================================================
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Total validation files: {total_files}
Passed: {passed_files}
Failed: {total_files - passed_files}
Pass rate: {pass_rate:.1f}%
Duration: {total_time:.1f}s
Status: {status}

This report is offline validation only. It does not approve live trading,
broker execution, canaries, or real-money deployment.
======================================================================
"""


def main(argv=None) -> int:
    """Run the validation suite with offline-safe defaults."""
    parser = argparse.ArgumentParser(description="Offline-safe validation runner")
    parser.add_argument(
        "--allow-broker-network",
        action="store_true",
        help="Allow broker/network validation files to run",
    )
    parser.add_argument(
        "--allow-report-write",
        action="store_true",
        help="Write the validation summary artifact to disk",
    )
    args = parser.parse_args(argv)

    print("=" * 70)
    print("FULL TEST SUITE VALIDATION")
    print("Offline-safe validation; live trading approval is out of scope")
    print("=" * 70)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]}")

    all_results = []
    start_time = time.time()
    test_files_found = list(Path("validation/legacy").glob("test_*.py"))
    print(f"\nFound {len(test_files_found)} legacy validation files")

    for category_name, tests in TEST_CATEGORIES.items():
        if category_name == "Phase 4: Infrastructure & Broker Tests" and not args.allow_broker_network:
            print(f"\nSkipping {category_name}: requires --allow-broker-network")
            continue

        print(f"\n{'-' * 70}")
        print(f"Starting: {category_name}")
        print("-" * 70)
        category_results = []
        for test_file, timeout in tests:
            if Path(test_file).exists():
                print(f"Running: {test_file}...", end=" ", flush=True)
                result = run_test(test_file, timeout, args.allow_broker_network)
                category_results.append(result)
                all_results.append(result)
                print(f"{'PASS' if result['passed'] else 'FAIL'} ({result['elapsed']:.1f}s)")
            else:
                print(f"Skipping: {test_file} (not found)")
        print_results(category_results, category_name)

    total_time = time.time() - start_time
    total_passed = sum(1 for result in all_results if result["passed"])
    total_tests = len(all_results)
    overall_pass_rate = (total_passed / total_tests * 100) if total_tests else 0.0

    print("\n" + "=" * 70)
    print("FINAL VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Total Files Tested: {total_tests}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_tests - total_passed}")
    print(f"Pass Rate: {overall_pass_rate:.1f}%")
    print(f"Total Duration: {total_time:.1f} seconds ({total_time / 60:.1f} minutes)")

    summary = generate_certificate(all_results, total_time)
    print(summary)

    if args.allow_report_write:
        summary_file = f"OFFLINE_VALIDATION_SUMMARY_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(summary_file, "w", encoding="utf-8") as handle:
            handle.write(summary)
        print(f"Summary saved to: {summary_file}")
    else:
        print("Summary artifact write skipped; use --allow-report-write to write a file.")

    if overall_pass_rate == 100:
        print("\nOffline validation passed. Live trading remains locked behind explicit safety gates.")
        return 0

    print(f"\nReview required: system has {total_tests - total_passed} failing validation file(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
