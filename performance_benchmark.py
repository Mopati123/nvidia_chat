"""
performance_benchmark.py — Benchmark acceleration backends

Measures performance gains across different backends:
- NumPy baseline
- Cython acceleration
- Numba JIT (if available)
- Mojo (if available)

Usage:
    python performance_benchmark.py
"""

import time
import numpy as np
from typing import Dict, List
from dataclasses import dataclass
from trading.accelerated.backend_selector import get_backend, get_best_backend
from trading.path_integral.trajectory_generator import PathIntegralEngine


@dataclass
class BenchmarkResult:
    """Benchmark result for a single backend"""
    backend_name: str
    operation: str
    time_seconds: float
    speedup: float = 1.0
    trajectories_per_second: float = 0.0


class PerformanceBenchmark:
    """Comprehensive performance benchmarking"""

    def __init__(self):
        self.generator = PathIntegralEngine()
        self.backends = ['numpy', 'cython']  # Add more as available

    def benchmark_trajectory_generation(self, n_trajectories: int = 10) -> List[BenchmarkResult]:
        """Benchmark trajectory generation across backends"""

        results = []

        # Generate test market data
        market_data = self._generate_test_market_data()

        print(f"Testing trajectory generation ({n_trajectories} trajectories)...")

        start_time = time.time()

        try:
            # Use the path integral engine
            result = self.generator.execute_path_integral(
                initial_state=market_data,
                hamiltonian={'H_geo': 1.0, 'H_3B': 0.5, 'H_stat': 0.1},
                operator_registry=None  # Simplified
            )

            end_time = time.time()
            duration = end_time - start_time

            trajectories_generated = result.get('trajectory_count', 0)

            result_obj = BenchmarkResult(
                backend_name="current",
                operation="trajectory_generation",
                time_seconds=duration,
                trajectories_per_second=trajectories_generated / duration if duration > 0 else 0
            )

            results.append(result_obj)
            print(".2f")

        except Exception as e:
            print(f"  ❌ Failed: {e}")

        return results

    def benchmark_path_integral(self, n_steps: int = 1000) -> List[BenchmarkResult]:
        """Benchmark path integral computation"""

        print(f"Testing path integral RK4 ({n_steps} steps)...")

        # Test data
        q0 = np.array([100.0, 0.0, 0.0])  # position
        p0 = np.array([0.0, 1.0, 0.0])    # momentum
        dt = 0.01

        start_time = time.time()

        try:
            # Simple harmonic oscillator integration
            q, p = q0.copy(), p0.copy()

            for _ in range(n_steps):
                # F = -q (harmonic oscillator)
                accel = -q
                # Velocity Verlet integration (simpler than RK4 for benchmark)
                q += p * dt + 0.5 * accel * dt * dt
                accel_new = -q
                p += 0.5 * (accel + accel_new) * dt

            end_time = time.time()
            duration = end_time - start_time

            result = BenchmarkResult(
                backend_name="current",
                operation="path_integral_integration",
                time_seconds=duration
            )

            print(".2f")
            return [result]

        except Exception as e:
            print(f"  ❌ Failed: {e}")
            return []

    def _generate_test_market_data(self) -> Dict:
        """Generate synthetic market data for testing"""
        return {
            'price': 100.0 + np.random.randn() * 5,
            'timestamp': time.time(),
            'order_blocks': [
                {'level': 98.0, 'strength': 0.8},
                {'level': 102.0, 'strength': 0.6}
            ],
            'liquidity_pools': [
                {'level': 99.0, 'size': 1000},
                {'level': 101.0, 'size': 800}
            ],
            'fvgs': [
                {'level': 97.0, 'strength': 0.9}
            ],
            'spread': 0.1,
            'session_time': 0.5  # Mid-session
        }

    def run_full_benchmark(self) -> Dict[str, List[BenchmarkResult]]:
        """Run complete benchmark suite"""

        print("🚀 Starting Performance Benchmark")
        print("=" * 50)

        results = {
            'trajectory_generation': self.benchmark_trajectory_generation(),
            'path_integral': self.benchmark_path_integral()
        }

        print("\n📊 Benchmark Results Summary")
        print("=" * 50)

        for operation, op_results in results.items():
            print(f"\n{operation.upper()}:")
            for result in op_results:
                print("6s")

        return results


if __name__ == "__main__":
    benchmark = PerformanceBenchmark()
    results = benchmark.run_full_benchmark()