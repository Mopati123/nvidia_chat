"""
Full Test Suite Validation
Comprehensive test battery for production readiness
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

# Test categories with expected durations
TEST_CATEGORIES = {
    'Phase 1: Smoke Tests (Fast)': [
        ('scripts/validation/preflight_check.py', 30),
        ('validation/legacy/test_production_system.py', 60),
    ],
    'Phase 2: Core Feature Tests': [
        ('validation/legacy/test_taep_integration.py', 30),
        ('validation/legacy/test_riemannian_geometry.py', 30),
        ('validation/legacy/test_microstructure_integration.py', 30),
        ('validation/legacy/test_nn_integration.py', 30),
        ('validation/legacy/test_rl_integration.py', 30),
        ('validation/legacy/test_memory_integration.py', 30),
    ],
    'Phase 3: System Integration Tests': [
        ('validation/legacy/test_complete_system_e2e.py', 120),
        ('validation/legacy/test_full_system.py', 60),
        ('validation/legacy/test_integration.py', 30),
        ('validation/legacy/test_integration_final.py', 30),
    ],
    'Phase 4: Infrastructure & Broker Tests': [
        ('validation/legacy/test_deriv_connection.py', 30),
        ('validation/legacy/test_shadow_live.py', 30),
        ('validation/legacy/test_multi_agent.py', 30),
    ],
    'Phase 5: Specialized Tests': [
        ('validation/legacy/test_superposition.py', 30),
        ('validation/legacy/test_strategy_agent.py', 30),
        ('validation/legacy/test_acceleration.py', 30),
        ('validation/legacy/test_coherence_audit.py', 30),
    ],
}


def run_test(test_file: str, timeout: int) -> dict:
    """Run a single test file and return results"""
    start = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()
        )
        
        elapsed = time.time() - start
        passed = result.returncode == 0
        
        # Parse output for test counts
        output = result.stdout + result.stderr
        passed_count = output.count('[PASS]') + output.count('PASS:')
        failed_count = output.count('[FAIL]') + output.count('FAILED')
        
        return {
            'file': test_file,
            'passed': passed,
            'returncode': result.returncode,
            'elapsed': elapsed,
            'passed_count': passed_count,
            'failed_count': failed_count,
            'output': output[-2000:] if len(output) > 2000 else output  # Last 2000 chars
        }
        
    except subprocess.TimeoutExpired:
        return {
            'file': test_file,
            'passed': False,
            'error': 'Timeout',
            'elapsed': timeout,
            'passed_count': 0,
            'failed_count': 0,
            'output': 'Test timed out'
        }
    except Exception as e:
        return {
            'file': test_file,
            'passed': False,
            'error': str(e),
            'elapsed': 0,
            'passed_count': 0,
            'failed_count': 0,
            'output': str(e)
        }


def print_results(results: list, category: str):
    """Print test results for a category"""
    print(f"\n{'='*70}")
    print(f"{category}")
    print('='*70)
    
    category_passed = 0
    category_total = len(results)
    
    for result in results:
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        print(f"{status} {result['file']:<40} ({result['elapsed']:.1f}s)")
        
        if result['passed']:
            category_passed += 1
        else:
            # Print error details for failed tests
            if 'error' in result:
                print(f"     Error: {result['error']}")
            elif result.get('failed_count', 0) > 0:
                print(f"     Failed tests: {result['failed_count']}")
    
    print(f"\nCategory: {category_passed}/{category_total} files passed")
    
    return category_passed, category_total


def generate_certificate(all_results: list, total_time: float) -> str:
    """Generate production readiness certificate"""
    total_files = len(all_results)
    passed_files = sum(1 for r in all_results if r['passed'])
    pass_rate = (passed_files / total_files * 100) if total_files > 0 else 0
    
    cert = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║           PRODUCTION READINESS CERTIFICATE                                   ║
║                                                                              ║
║  System: Quantum Trading Platform with TAEP Governance                       ║
║  Validation Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                       ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  TEST RESULTS SUMMARY                                                        ║
║  ─────────────────────                                                       ║
║  Total Test Files:    {total_files:>3}                                                  ║
║  Passed:              {passed_files:>3}                                                  ║
║  Failed:              {total_files - passed_files:>3}                                                  ║
║  Pass Rate:           {pass_rate:>5.1f}%                                               ║
║  Total Duration:      {total_time:>5.1f}s                                              ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  CERTIFICATION STATUS: {'✅ PRODUCTION READY' if pass_rate == 100 else '❌ NOT READY'}                              ║
║                                                                              ║
║  The system has {'successfully passed' if pass_rate == 100 else 'not passed'} all validation tests                     ║
║  and is {'approved' if pass_rate == 100 else 'not approved'} for world deployment.                                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    return cert


def main():
    """Run full test suite validation"""
    print("="*70)
    print("FULL TEST SUITE VALIDATION")
    print("Production Readiness for World Deployment")
    print("="*70)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]}")
    print("="*70)
    
    all_results = []
    start_time = time.time()
    
    # Check for test files
    test_dir = Path('validation/legacy')
    test_files_found = list(test_dir.glob('test_*.py'))
    print(f"\nFound {len(test_files_found)} test files in directory")
    
    # Run tests by category
    for category_name, tests in TEST_CATEGORIES.items():
        print(f"\n{'─'*70}")
        print(f"Starting: {category_name}")
        print('─'*70)
        
        category_results = []
        for test_file, timeout in tests:
            if Path(test_file).exists():
                print(f"Running: {test_file}...", end=' ', flush=True)
                result = run_test(test_file, timeout)
                category_results.append(result)
                all_results.append(result)
                print(f"{'✅' if result['passed'] else '❌'} ({result['elapsed']:.1f}s)")
            else:
                print(f"Skipping: {test_file} (not found)")
        
        # Print category summary
        cat_passed, cat_total = print_results(category_results, category_name)
    
    total_time = time.time() - start_time
    
    # Final summary
    print("\n" + "="*70)
    print("FINAL VALIDATION SUMMARY")
    print("="*70)
    
    total_passed = sum(1 for r in all_results if r['passed'])
    total_tests = len(all_results)
    overall_pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\nTotal Files Tested: {total_tests}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_tests - total_passed}")
    print(f"Pass Rate: {overall_pass_rate:.1f}%")
    print(f"Total Duration: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
    
    # Print certificate
    cert = generate_certificate(all_results, total_time)
    print(cert)
    
    # Save certificate to file
    cert_file = f"PRODUCTION_CERTIFICATE_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(cert_file, 'w', encoding='utf-8') as f:
        f.write(cert)
    print(f"Certificate saved to: {cert_file}")
    
    # Return appropriate exit code
    if overall_pass_rate == 100:
        print("\n🎉 SYSTEM IS PRODUCTION READY FOR WORLD DEPLOYMENT! 🎉")
        return 0
    else:
        print(f"\n⚠️  System has {total_tests - total_passed} failing test(s). Review required.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
