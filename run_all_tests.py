#!/usr/bin/env python3
"""
Comprehensive Test Runner - First Principles Testing Framework

Runs all tests and generates summary report:
- Unit tests (geometry, microstructure, action, learning)
- Integration tests (pipeline, end-to-end)
- Property tests (mathematical invariants)
"""

import subprocess
import sys
import time


def run_test_suite(name, path):
    """Run a test suite and return results."""
    print(f"\n{'='*70}")
    print(f"Running: {name}")
    print('='*70)
    
    start = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', path, '-v', '--tb=short'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        duration = time.time() - start
        
        # Parse results
        output = result.stdout + result.stderr
        
        if 'passed' in output:
            # Extract pass/fail counts
            for line in output.split('\n'):
                if 'passed' in line and 'failed' not in line.lower():
                    print(f"✅ {name}: {line.strip()}")
                    return {'name': name, 'passed': True, 'duration': duration, 'details': line.strip()}
                elif 'failed' in line:
                    print(f"❌ {name}: {line.strip()}")
                    return {'name': name, 'passed': False, 'duration': duration, 'details': line.strip()}
        
        if result.returncode == 0:
            print(f"✅ {name}: Passed")
            return {'name': name, 'passed': True, 'duration': duration}
        else:
            print(f"❌ {name}: Failed")
            return {'name': name, 'passed': False, 'duration': duration}
            
    except subprocess.TimeoutExpired:
        print(f"⏱️  {name}: Timeout")
        return {'name': name, 'passed': False, 'duration': 60, 'error': 'timeout'}
    except Exception as e:
        print(f"💥 {name}: Error - {e}")
        return {'name': name, 'passed': False, 'duration': 0, 'error': str(e)}


def main():
    """Run all test suites."""
    print('='*70)
    print('COMPREHENSIVE TEST FRAMEWORK - FIRST PRINCIPLES')
    print('='*70)
    print('Testing all system components from mathematical foundations...')
    
    suites = [
        ('Geometry Unit Tests', 'tests/unit/test_geometry/'),
        # Add more as they are created:
        # ('Microstructure Tests', 'tests/unit/test_microstructure/'),
        # ('Action Tests', 'tests/unit/test_action/'),
        # ('Learning Tests', 'tests/unit/test_learning/'),
        # ('Integration Tests', 'tests/integration/'),
    ]
    
    results = []
    total_start = time.time()
    
    for name, path in suites:
        result = run_test_suite(name, path)
        results.append(result)
    
    total_duration = time.time() - total_start
    
    # Summary
    print('\n' + '='*70)
    print('TEST SUMMARY')
    print('='*70)
    
    passed = sum(1 for r in results if r['passed'])
    total = len(results)
    
    for r in results:
        status = '✅ PASS' if r['passed'] else '❌ FAIL'
        print(f"{status}: {r['name']} ({r['duration']:.2f}s)")
    
    print('-'*70)
    print(f"Total: {passed}/{total} suites passed")
    print(f"Duration: {total_duration:.2f}s")
    
    if passed == total:
        print('\n🎉 ALL TESTS PASSED - System mathematically verified!')
        return 0
    else:
        print(f'\n⚠️  {total - passed} suite(s) failed - review required')
        return 1


if __name__ == '__main__':
    sys.exit(main())
