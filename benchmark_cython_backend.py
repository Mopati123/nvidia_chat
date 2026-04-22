"""
benchmark_cython_backend.py — Test Cython acceleration performance
"""

import time
import numpy as np
from trading.accelerated.backend_selector import AcceleratedBackend

def benchmark_backend(backend_name: str, n_runs: int = 100):
    """Benchmark a specific backend"""
    print(f"\n=== Benchmarking {backend_name} backend ===")

    backend = AcceleratedBackend(preferred=backend_name)

    # Test parameters
    initial_price = 1.0850
    initial_velocity = 0.0
    dt = 0.1
    n_steps = 50
    potential_force = 0.01
    noise_scale = 0.001

    start_time = time.time()

    for i in range(n_runs):
        path = backend.rk4_integrate(
            initial_price, initial_velocity, dt, n_steps,
            potential_force, noise_scale
        )

    end_time = time.time()
    total_time = end_time - start_time

    rate = n_runs / total_time
    print(".2f")
    print(".4f")

    return rate

def main():
    """Run all backend benchmarks"""
    print("ApexQuantumICT Backend Performance Benchmark")
    print("=" * 50)

    backends = ['numpy', 'numba', 'cython']
    results = {}

    for backend in backends:
        try:
            rate = benchmark_backend(backend, n_runs=1000)
            results[backend] = rate
        except Exception as e:
            print(f"❌ {backend} backend failed: {e}")
            results[backend] = 0

    print("\n" + "=" * 50)
    print("PERFORMANCE COMPARISON:")
    print("=" * 50)

    baseline = results.get('numpy', 1)
    for backend, rate in results.items():
        if rate > 0:
            speedup = rate / baseline
            print("2d")

if __name__ == "__main__":
    main()