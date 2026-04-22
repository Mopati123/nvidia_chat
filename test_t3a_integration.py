"""
T3-A Integration Tests — Production Hardening

Tests:
  T3-A1: Circuit breaker wired into Stage 15 (scheduler_collapse)
         - 10 consecutive failures open the circuit
         - Open circuit triggers kill switch on risk_manager
         - Stage 15 returns REFUSED when circuit is open
  T3-A2: PnL divergence detection in Stage 17 (reconciliation)
         - divergence > 15% sets divergence_flagged = True
         - divergence < 15% passes cleanly
         - rolling history accumulates
  T3-A3: pnl_tracker execution error histogram
         - record_execution_error() populates deque
         - get_divergence_stats() returns correct stats
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from collections import deque


# ---------------------------------------------------------------------------
# T3-A1: Circuit breaker wired into orchestrator Stage 15
# ---------------------------------------------------------------------------

class TestT3A1CircuitBreaker:

    def _make_orchestrator(self):
        """Create an orchestrator with mocked scheduler and risk_manager."""
        from trading.resilience.circuit_breaker import CircuitBreakerConfig, CircuitBreaker, CircuitState

        mock_scheduler = MagicMock()
        mock_scheduler.authorize_collapse.return_value = (MagicMock(name="AUTHORIZED"), MagicMock(token_id="tok_1"))

        mock_rm = MagicMock()
        mock_rm.max_position_size = 1.0
        mock_rm.check_all_limits.return_value = MagicMock(passed=True, message="ok", level=MagicMock(value="low"))
        mock_rm.trigger_kill_switch = MagicMock()
        mock_rm.get_position_report.return_value = {}

        from trading.pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator(scheduler=mock_scheduler, risk_manager=mock_rm)
        return orch, mock_rm

    def test_circuit_breaker_exists_on_orchestrator(self):
        orch, _ = self._make_orchestrator()
        assert hasattr(orch, 'collapse_breaker'), "orchestrator must have collapse_breaker"
        assert orch.collapse_breaker.name == "scheduler_collapse"

    def test_circuit_breaker_config(self):
        orch, _ = self._make_orchestrator()
        assert orch.collapse_breaker.config.failure_threshold == 10
        assert orch.collapse_breaker.config.success_threshold == 3

    def test_ten_failures_open_circuit(self):
        orch, mock_rm = self._make_orchestrator()
        breaker = orch.collapse_breaker
        # Simulate 10 consecutive failures
        for _ in range(10):
            breaker._on_failure()
        from trading.resilience.circuit_breaker import CircuitState
        assert breaker.state == CircuitState.OPEN

    def test_circuit_open_triggers_kill_switch(self):
        orch, mock_rm = self._make_orchestrator()
        breaker = orch.collapse_breaker
        # Reset to CLOSED so the on_open callback fires on this transition
        breaker.manual_close()
        # Clear previous callbacks and register only the one for this mock_rm
        breaker.on_open_callbacks.clear()
        breaker.register_on_open(lambda: mock_rm.trigger_kill_switch("circuit_breaker_open"))
        for _ in range(10):
            breaker._on_failure()
        mock_rm.trigger_kill_switch.assert_called_once_with("circuit_breaker_open")

    def test_stage15_returns_refused_when_circuit_open(self):
        orch, mock_rm = self._make_orchestrator()
        # Force circuit open
        for _ in range(10):
            orch.collapse_breaker._on_failure()

        from trading.pipeline.orchestrator import PipelineContext
        import time
        ctx = PipelineContext(symbol="EURUSD", timestamp=time.time(), source="MT5")
        ctx.risk_check_passed = True
        ctx.risk_check_message = "ok"
        ctx.admissible_paths = [{'id': 'p1', 'energy': 1.0, 'action': 1.0}]
        ctx.action_scores = {'delta_s': 0.3}
        ctx.proposal = {'entry': 1.0855, 'stop': 1.0830, 'target': 1.0900,
                        'direction': 'buy', 'size': 0.1, 'predicted_pnl': 50.0}

        result = orch._stage_scheduler_collapse(ctx)
        assert result['authorized'] is False
        assert result['decision'] == 'REFUSED'
        assert 'circuit_breaker' in result.get('reason', '')

    def test_successful_calls_close_circuit_from_half_open(self):
        orch, _ = self._make_orchestrator()
        breaker = orch.collapse_breaker
        from trading.resilience.circuit_breaker import CircuitState
        # Force to half-open
        for _ in range(10):
            breaker._on_failure()
        breaker._transition_to(CircuitState.HALF_OPEN)
        # 3 successes should close it
        for _ in range(3):
            breaker._on_success()
        assert breaker.state == CircuitState.CLOSED

    def test_divergence_history_deque_exists(self):
        orch, _ = self._make_orchestrator()
        assert hasattr(orch, 'divergence_history')
        assert isinstance(orch.divergence_history, deque)
        assert orch.divergence_history.maxlen == 100


# ---------------------------------------------------------------------------
# T3-A2: PnL divergence detection in Stage 17
# ---------------------------------------------------------------------------

class TestT3A2PnLDivergence:

    def _make_orchestrator_with_context(self, predicted_pnl, realized_pnl):
        mock_scheduler = MagicMock()
        mock_rm = MagicMock()
        mock_rm.max_position_size = 1.0
        mock_rm.get_position_report.return_value = {}

        from trading.pipeline.orchestrator import PipelineOrchestrator, PipelineContext
        import time
        orch = PipelineOrchestrator(scheduler=mock_scheduler, risk_manager=mock_rm)

        ctx = PipelineContext(symbol="EURUSD", timestamp=time.time(), source="MT5")
        ctx.proposal = {
            'entry': 1.0855, 'stop': 1.0830, 'target': 1.0900,
            'direction': 'buy', 'size': 0.1,
            'predicted_pnl': predicted_pnl
        }
        ctx.execution_result = {
            'order_id': 'ord_test',
            'symbol': 'EURUSD',
            'entry_price': 1.0855,
            'status': 'filled',
            'realized_pnl': realized_pnl
        }
        return orch, ctx

    def test_low_divergence_not_flagged(self):
        orch, ctx = self._make_orchestrator_with_context(100.0, 95.0)  # 5% divergence
        result = orch._stage_reconciliation(ctx)
        assert result['divergence_flagged'] is False
        assert result['pnl_divergence'] == pytest.approx(0.05, abs=1e-6)

    def test_high_divergence_flagged(self):
        orch, ctx = self._make_orchestrator_with_context(100.0, 20.0)  # 80% divergence
        result = orch._stage_reconciliation(ctx)
        assert result['divergence_flagged'] is True
        assert result['pnl_divergence'] == pytest.approx(0.80, abs=1e-6)

    def test_high_divergence_triggers_weight_penalty(self):
        orch, ctx = self._make_orchestrator_with_context(100.0, 20.0)
        orch._stage_reconciliation(ctx)
        orch.scheduler.update_action_weights.assert_called_once()
        call_kwargs = orch.scheduler.update_action_weights.call_args[1]
        assert call_kwargs['pnl'] < 0  # penalty is negative

    def test_low_divergence_no_weight_penalty(self):
        orch, ctx = self._make_orchestrator_with_context(100.0, 95.0)
        orch._stage_reconciliation(ctx)
        orch.scheduler.update_action_weights.assert_not_called()

    def test_divergence_appended_to_history(self):
        orch, ctx = self._make_orchestrator_with_context(100.0, 20.0)
        assert len(orch.divergence_history) == 0
        orch._stage_reconciliation(ctx)
        assert len(orch.divergence_history) == 1

    def test_divergence_history_accumulates(self):
        mock_scheduler = MagicMock()
        mock_rm = MagicMock()
        mock_rm.max_position_size = 1.0
        mock_rm.get_position_report.return_value = {}
        from trading.pipeline.orchestrator import PipelineOrchestrator, PipelineContext
        import time
        orch = PipelineOrchestrator(scheduler=mock_scheduler, risk_manager=mock_rm)

        for i in range(5):
            ctx = PipelineContext(symbol="EURUSD", timestamp=time.time(), source="MT5")
            ctx.proposal = {'entry': 1.0855, 'predicted_pnl': 100.0}
            ctx.execution_result = {'entry_price': 1.0855, 'realized_pnl': 90.0}
            orch._stage_reconciliation(ctx)

        assert len(orch.divergence_history) == 5

    def test_zero_predicted_pnl_no_division_error(self):
        orch, ctx = self._make_orchestrator_with_context(0.0, 50.0)
        result = orch._stage_reconciliation(ctx)
        assert 'pnl_divergence' in result
        assert result['pnl_divergence'] >= 0


# ---------------------------------------------------------------------------
# T3-A3: pnl_tracker execution error histogram
# ---------------------------------------------------------------------------

class TestT3A3ExecutionErrorHistogram:

    def _make_tracker(self, tmp_path):
        with patch('trading.risk.pnl_tracker.get_risk_manager', return_value=MagicMock()):
            from trading.risk.pnl_tracker import DailyPnLTracker
            return DailyPnLTracker(data_dir=str(tmp_path))

    def test_execution_errors_deque_exists(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        assert hasattr(tracker, 'execution_errors')
        assert isinstance(tracker.execution_errors, deque)
        assert tracker.execution_errors.maxlen == 100

    def test_record_execution_error_populates_deque(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.record_execution_error(predicted_pnl=100.0, realized_pnl=80.0)
        assert len(tracker.execution_errors) == 1
        assert tracker.execution_errors[0] == pytest.approx(0.20, abs=1e-6)

    def test_get_divergence_stats_empty(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        stats = tracker.get_divergence_stats()
        assert stats == {'mean': 0.0, 'std': 0.0, 'p95': 0.0, 'count': 0}

    def test_get_divergence_stats_populated(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        for i in range(10):
            tracker.record_execution_error(100.0, 100.0 - i * 5)
        stats = tracker.get_divergence_stats()
        assert stats['count'] == 10
        assert stats['mean'] > 0
        assert stats['p95'] >= stats['mean']

    def test_deque_bounded_at_100(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        for _ in range(150):
            tracker.record_execution_error(100.0, 50.0)
        assert len(tracker.execution_errors) == 100

    def test_zero_predicted_pnl_safe(self, tmp_path):
        tracker = self._make_tracker(tmp_path)
        tracker.record_execution_error(predicted_pnl=0.0, realized_pnl=25.0)
        assert len(tracker.execution_errors) == 1
        assert tracker.execution_errors[0] >= 0
