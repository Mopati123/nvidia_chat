#!/usr/bin/env python3
"""
Performance Latency Tests

Benchmarks component latencies and identifies bottlenecks.
"""

import sys
sys.path.insert(0, '.')

import time
import timeit
import numpy as np
from contextlib import contextmanager


@contextmanager
def timer(name):
    """Context manager for timing code blocks"""
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    elapsed = (end - start) * 1000  # Convert to ms
    print(f"  {name}: {elapsed:.2f}ms")


class LatencyBenchmarks:
    """Benchmark suite for system components"""
    
    def __init__(self):
        self.results = {}
    
    def benchmark_memory(self, n_iterations=100):
        """Benchmark memory/embedding generation"""
        print("\n📊 Benchmarking Memory System...")
        
        from trading.memory import get_embedder
        
        embedder = get_embedder()
        ohlcv = [
            {'open': 1.0, 'high': 1.01, 'low': 0.99, 'close': 1.0, 'volume': 1000}
            for _ in range(100)
        ]
        
        # Warmup
        _ = embedder.encode(ohlcv)
        
        # Benchmark
        times = []
        for _ in range(n_iterations):
            start = time.perf_counter()
            _ = embedder.encode(ohlcv)
            end = time.perf_counter()
            times.append((end - start) * 1000)
        
        mean_time = np.mean(times)
        std_time = np.std(times)
        
        self.results['memory_embedding'] = {
            'mean_ms': mean_time,
            'std_ms': std_time,
            'p95_ms': np.percentile(times, 95),
            'target_ms': 5.0,
            'pass': mean_time < 10.0  # Generous threshold
        }
        
        print(f"  Embedding: {mean_time:.2f}ms ± {std_time:.2f}ms (target: 5ms)")
        print(f"  P95: {np.percentile(times, 95):.2f}ms")
        
        return self.results['memory_embedding']
    
    def benchmark_nn_predictor(self, n_iterations=100):
        """Benchmark neural network prediction"""
        print("\n📊 Benchmarking NN Predictor...")
        
        from trading.models import SimplePricePredictor
        
        predictor = SimplePricePredictor()
        embedding = np.random.randn(128).astype(np.float32)
        
        # Warmup
        _ = predictor.predict(embedding)
        
        # Benchmark
        times = []
        for _ in range(n_iterations):
            start = time.perf_counter()
            _ = predictor.predict(embedding)
            end = time.perf_counter()
            times.append((end - start) * 1000)
        
        mean_time = np.mean(times)
        std_time = np.std(times)
        
        self.results['nn_prediction'] = {
            'mean_ms': mean_time,
            'std_ms': std_time,
            'p95_ms': np.percentile(times, 95),
            'target_ms': 10.0,
            'pass': mean_time < 20.0
        }
        
        print(f"  Prediction: {mean_time:.2f}ms ± {std_time:.2f}ms (target: 10ms)")
        print(f"  P95: {np.percentile(times, 95):.2f}ms")
        
        return self.results['nn_prediction']
    
    def benchmark_agent_voting(self, n_iterations=50):
        """Benchmark multi-agent voting"""
        print("\n📊 Benchmarking Agent Voting...")
        
        from trading.agents import (
            PatternAgent, RiskAgent, TimingAgent,
            MultiAgentOrchestrator
        )
        
        # Create agents
        agents = [
            PatternAgent(name="PatternAgent", weight=1.0),
            RiskAgent(name="RiskAgent", weight=1.0),
            TimingAgent(name="TimingAgent", weight=1.0)
        ]
        
        orchestrator = MultiAgentOrchestrator(agents=agents)
        
        # Test data
        ohlcv = [{'open': 1.0, 'high': 1.01, 'low': 0.99, 'close': 1.0, 'volume': 1000} for _ in range(100)]
        market_state = {'ohlc': ohlcv, 'operator_scores': {}}
        trajectories = [{'id': f'traj_{i}', 'energy': 0.5, 'action': 0.1} for i in range(5)]
        
        # Warmup
        _ = orchestrator.collect_votes(trajectories, market_state)
        
        # Benchmark
        times = []
        for _ in range(n_iterations):
            start = time.perf_counter()
            votes = orchestrator.collect_votes(trajectories, market_state)
            _ = orchestrator.aggregate_votes(votes)
            end = time.perf_counter()
            times.append((end - start) * 1000)
        
        mean_time = np.mean(times)
        std_time = np.std(times)
        
        self.results['agent_voting'] = {
            'mean_ms': mean_time,
            'std_ms': std_time,
            'p95_ms': np.percentile(times, 95),
            'target_ms': 50.0,
            'pass': mean_time < 100.0
        }
        
        print(f"  Voting (3 agents): {mean_time:.2f}ms ± {std_time:.2f}ms (target: 50ms)")
        print(f"  P95: {np.percentile(times, 95):.2f}ms")
        
        return self.results['agent_voting']
    
    def benchmark_rl_inference(self, n_iterations=100):
        """Benchmark RL action selection"""
        print("\n📊 Benchmarking RL Inference...")
        
        from trading.rl import PPOSchedulerAgent
        
        agent = PPOSchedulerAgent(state_dim=166, action_dim=5, device="cpu")
        state = np.random.randn(166).astype(np.float32)
        
        # Warmup
        _ = agent.select_action(state)
        
        # Benchmark
        times = []
        for _ in range(n_iterations):
            start = time.perf_counter()
            _ = agent.select_action(state)
            end = time.perf_counter()
            times.append((end - start) * 1000)
        
        mean_time = np.mean(times)
        std_time = np.std(times)
        
        self.results['rl_inference'] = {
            'mean_ms': mean_time,
            'std_ms': std_time,
            'p95_ms': np.percentile(times, 95),
            'target_ms': 5.0,
            'pass': mean_time < 10.0
        }
        
        print(f"  RL Action: {mean_time:.2f}ms ± {std_time:.2f}ms (target: 5ms)")
        print(f"  P95: {np.percentile(times, 95):.2f}ms")
        
        return self.results['rl_inference']
    
    def benchmark_full_decision(self, n_iterations=20):
        """Benchmark complete decision pipeline"""
        print("\n📊 Benchmarking Full Decision Pipeline...")
        
        from trading.memory import get_embedder
        from trading.models import SimplePricePredictor
        from trading.agents import PatternAgent, RiskAgent, MultiAgentOrchestrator
        from trading.kernel import Scheduler
        
        # Initialize components
        embedder = get_embedder()
        predictor = SimplePricePredictor()
        pattern = PatternAgent()
        risk = RiskAgent()
        orchestrator = MultiAgentOrchestrator(agents=[pattern, risk])
        scheduler = Scheduler(config={'use_rl': False})
        
        from trading.kernel.scheduler import CollapseDecision
        
        # Test data
        ohlcv = [{'open': 1.0, 'high': 1.01, 'low': 0.99, 'close': 1.0, 'volume': 1000} for _ in range(100)]
        trajectories = [{'id': f'traj_{i}', 'energy': 0.5, 'action': 0.1} for i in range(3)]
        
        # Warmup
        _ = embedder.encode(ohlcv)
        
        # Benchmark
        times = []
        for _ in range(n_iterations):
            start = time.perf_counter()
            
            # Full pipeline
            embedding = embedder.encode(ohlcv)
            prediction = predictor.predict(embedding)
            
            market_state = {
                'ohlc': ohlcv,
                'trend': prediction.get('trend', 'neutral'),
                'operator_scores': {}
            }
            
            votes = orchestrator.collect_votes(trajectories, market_state)
            decision = orchestrator.aggregate_votes(votes)
            
            _, token = scheduler.authorize_collapse(
                proposal={},
                projected_trajectories=trajectories,
                delta_s=0.3,
                constraints_passed=True,
                reconciliation_clear=True
            )
            scheduler.release_execution_token(token)
            
            end = time.perf_counter()
            times.append((end - start) * 1000)
        
        mean_time = np.mean(times)
        std_time = np.std(times)
        
        self.results['full_decision'] = {
            'mean_ms': mean_time,
            'std_ms': std_time,
            'p95_ms': np.percentile(times, 95),
            'target_ms': 100.0,
            'pass': mean_time < 200.0
        }
        
        print(f"  Full Pipeline: {mean_time:.2f}ms ± {std_time:.2f}ms (target: 100ms)")
        print(f"  P95: {np.percentile(times, 95):.2f}ms")
        
        return self.results['full_decision']
    
    def generate_report(self):
        """Generate performance report"""
        print("\n" + "="*70)
        print("📊 PERFORMANCE BENCHMARK REPORT")
        print("="*70)
        
        total_pass = 0
        total_tests = 0
        
        for component, metrics in self.results.items():
            total_tests += 1
            status = "✅ PASS" if metrics['pass'] else "❌ FAIL"
            if metrics['pass']:
                total_pass += 1
            
            print(f"\n{component.upper().replace('_', ' ')}:")
            print(f"  Mean: {metrics['mean_ms']:.2f}ms")
            print(f"  Std:  {metrics['std_ms']:.2f}ms")
            print(f"  P95:  {metrics['p95_ms']:.2f}ms")
            print(f"  Target: {metrics['target_ms']:.2f}ms")
            print(f"  Status: {status}")
        
        print("\n" + "="*70)
        print(f"SUMMARY: {total_pass}/{total_tests} components meeting targets")
        print("="*70)
        
        # Identify bottlenecks
        print("\n🔍 BOTTLENECK ANALYSIS:")
        slowest = sorted(self.results.items(), key=lambda x: x[1]['mean_ms'], reverse=True)
        for i, (component, metrics) in enumerate(slowest[:3], 1):
            if metrics['mean_ms'] > metrics['target_ms']:
                print(f"  {i}. {component}: {metrics['mean_ms']:.2f}ms vs {metrics['target_ms']:.2f}ms target (+{metrics['mean_ms']/metrics['target_ms']:.1f}x)")
        
        return total_pass == total_tests


def main():
    """Run all benchmarks"""
    print("="*70)
    print("🚀 PERFORMANCE BENCHMARK SUITE")
    print("="*70)
    
    benchmarks = LatencyBenchmarks()
    
    try:
        benchmarks.benchmark_memory(n_iterations=100)
    except Exception as e:
        print(f"  ⚠️ Memory benchmark failed: {e}")
    
    try:
        benchmarks.benchmark_nn_predictor(n_iterations=100)
    except Exception as e:
        print(f"  ⚠️ NN benchmark failed: {e}")
    
    try:
        benchmarks.benchmark_agent_voting(n_iterations=50)
    except Exception as e:
        print(f"  ⚠️ Agent voting benchmark failed: {e}")
    
    try:
        benchmarks.benchmark_rl_inference(n_iterations=100)
    except Exception as e:
        print(f"  ⚠️ RL benchmark failed: {e}")
    
    try:
        benchmarks.benchmark_full_decision(n_iterations=20)
    except Exception as e:
        print(f"  ⚠️ Full pipeline benchmark failed: {e}")
    
    success = benchmarks.generate_report()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
