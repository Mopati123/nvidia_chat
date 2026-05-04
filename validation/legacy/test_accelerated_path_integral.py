"""
validation/legacy/test_accelerated_path_integral.py — Test accelerated path integral performance
"""

import time
from trading.path_integral import PathIntegralEngine
from trading.operators.operator_registry import OperatorRegistry

def test_accelerated_path_integral():
    """Test path integral with acceleration"""
    print("Testing Accelerated Path Integral Engine")
    print("=" * 50)

    # Initialize components
    engine = PathIntegralEngine()
    operator_registry = OperatorRegistry()

    # Test parameters
    initial_state = {
        "price": 1.0850,
        "velocity": 0.0,
        "time": 0.0
    }

    hamiltonian = {
        "geometric": 0.01,
        "three_body": 0.005,
        "statistical": 0.002
    }

    # Benchmark
    n_runs = 10
    start_time = time.time()

    for i in range(n_runs):
        result = engine.execute_path_integral(
            initial_state, hamiltonian, operator_registry
        )
        print(f"Run {i+1}: Generated {result['trajectory_count']} trajectories, ε={result['epsilon']:.4f}")

    end_time = time.time()
    total_time = end_time - start_time

    rate = n_runs / total_time
    print(".2f")
    print(".4f")

    # Show sample result
    print("\nSample Result:")
    best = result['best_trajectory']
    if best:
        print(f"  Best trajectory action: {best['action']:.4f}")
        print(f"  Predicted PnL: {best['predicted_pnl']:.4f}")
        print(f"  Path length: {len(best['path'])}")

if __name__ == "__main__":
    test_accelerated_path_integral()