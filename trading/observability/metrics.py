"""
Prometheus-style metrics collector for the ApexQuantumICT pipeline.

Usage:
    from trading.observability.metrics import MetricsCollector
    m = MetricsCollector.get()
    m.record_stage("proposal_generation", 12.3)   # ms
    m.record_decision("AUTHORIZED")
    m.record_tick(source="deriv", latency_ms=0.6)

Expose via FastAPI:
    GET /prometheus  -> MetricsCollector.get().to_prometheus()
"""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from typing import Dict, List


class MetricsCollector:
    """Singleton — thread-safe metrics store for all 20 pipeline stages."""

    _instance: "MetricsCollector | None" = None
    _lock = Lock()

    def __init__(self) -> None:
        self._stage_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._decisions: Dict[str, int] = defaultdict(int)
        self._tick_latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._cb_transitions: List[str] = []
        self._divergence_values: deque = deque(maxlen=1000)
        self._mu = Lock()

    @classmethod
    def get(cls) -> "MetricsCollector":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_stage(self, name: str, ms: float) -> None:
        with self._mu:
            self._stage_times[name].append(ms)

    def record_decision(self, decision: str) -> None:
        with self._mu:
            self._decisions[decision] += 1

    def record_tick(self, source: str, latency_ms: float) -> None:
        with self._mu:
            self._tick_latencies[source].append(latency_ms)

    def record_cb_transition(self, state: str) -> None:
        with self._mu:
            self._cb_transitions.append(state)

    def record_divergence(self, ratio: float) -> None:
        with self._mu:
            self._divergence_values.append(ratio)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_prometheus(self) -> str:
        lines: List[str] = [
            "# HELP apex_stage_duration_ms Mean pipeline stage latency (ms)",
            "# TYPE apex_stage_duration_ms gauge",
        ]
        with self._mu:
            for stage, times in sorted(self._stage_times.items()):
                if times:
                    mean = sum(times) / len(times)
                    p95 = sorted(times)[int(len(times) * 0.95)]
                    lines.append(
                        f'apex_stage_duration_ms{{stage="{stage}",stat="mean"}} {mean:.3f}'
                    )
                    lines.append(
                        f'apex_stage_duration_ms{{stage="{stage}",stat="p95"}} {p95:.3f}'
                    )

            lines += [
                "",
                "# HELP apex_decisions_total Pipeline authorize/refuse counts",
                "# TYPE apex_decisions_total counter",
            ]
            for decision, count in sorted(self._decisions.items()):
                lines.append(
                    f'apex_decisions_total{{decision="{decision}"}} {count}'
                )

            lines += [
                "",
                "# HELP apex_tick_latency_ms Broker tick ingestion latency (ms)",
                "# TYPE apex_tick_latency_ms gauge",
            ]
            for source, lats in sorted(self._tick_latencies.items()):
                if lats:
                    mean = sum(lats) / len(lats)
                    lines.append(
                        f'apex_tick_latency_ms{{source="{source}"}} {mean:.3f}'
                    )

            lines += [
                "",
                "# HELP apex_pnl_divergence_ratio Mean predicted vs realized PnL divergence",
                "# TYPE apex_pnl_divergence_ratio gauge",
            ]
            if self._divergence_values:
                mean_div = sum(self._divergence_values) / len(self._divergence_values)
                lines.append(f"apex_pnl_divergence_ratio {mean_div:.6f}")

        return "\n".join(lines) + "\n"

    def summary(self) -> Dict:
        """Return a compact dict for the existing /metrics JSON endpoint."""
        with self._mu:
            stage_means = {}
            for stage, times in self._stage_times.items():
                if times:
                    stage_means[stage] = round(sum(times) / len(times), 2)
            div_mean = (
                sum(self._divergence_values) / len(self._divergence_values)
                if self._divergence_values else 0.0
            )
        return {
            "stage_latency_ms": stage_means,
            "decisions": dict(self._decisions),
            "pnl_divergence_mean": round(div_mean, 4),
        }
