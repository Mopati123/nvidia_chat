"""
shadow_trading_loop.py — Full shadow execution (no real capital)

Pre-collapse observation domain.
Papas observer: zero execution authority.
"""

import hashlib
import time
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from core.authority.token_validator import validate_token
from tachyonic_chain.audit_log import append_execution_evidence
from ..kernel.apex_engine import ApexEngine, ExecutionMode, ExecutionOutcome
from ..path_integral.trajectory_generator import PathIntegralEngine
from ..operators.operator_registry import OperatorRegistry
from ..market_bridge.minkowski_adapter import MarketDataAdapter


@dataclass
class ShadowExecution:
    """Record of shadow execution"""
    execution_id: str
    timestamp: float
    symbol: str
    bias: str
    outcome: ExecutionOutcome
    trajectory: Optional[Dict]
    evidence_hash: str
    operator_scores: Dict[str, float]
    pnl_prediction: float
    execution_time_ms: float


@dataclass
class DriftReport:
    """Shadow vs live drift detection"""
    shadow_execution: str
    hypothetical_live_result: float
    divergence: float
    threshold: float
    triggered: bool


class ShadowTradingLoop:
    """
    Full shadow execution engine.
    Runs complete canonical loop without committing capital.
    Generates performance metrics, drift reports, evidence bundles.
    """
    
    def __init__(self,
                 apex_engine: Optional[ApexEngine] = None,
                 path_engine: Optional[PathIntegralEngine] = None,
                 operator_registry: Optional[OperatorRegistry] = None):
        self.apex = apex_engine or ApexEngine()
        self.path_engine = path_engine or PathIntegralEngine()
        self.operators = operator_registry or OperatorRegistry()
        self.market_adapter = MarketDataAdapter()
        
        self.execution_history: List[ShadowExecution] = []
        self.drift_reports: List[DriftReport] = []
        self.performance_metrics: Dict[str, Any] = {
            "total_executions": 0,
            "refusals": 0,
            "successes": 0,
            "avg_execution_time_ms": 0.0,
            "cumulative_pnl": 0.0
        }
        
    def execute_shadow(self,
                      symbol: str,
                      ohlcv_data: List[Dict],
                      bias: str = "neutral",
                      session: str = "neutral",
                      token: Optional[Any] = None,
                      require_token: bool = False) -> ShadowExecution:
        """
        Execute full canonical cycle in shadow mode.
        
        Args:
            symbol: Trading pair (e.g., "EURUSD")
            ohlcv_data: List of OHLCV candles
            bias: Trading bias ("bullish", "bearish", "neutral")
            session: Trading session ("london", "ny", "asia")
        
        Returns:
            ShadowExecution: Full execution record with evidence
        """
        start_time = time.time()

        if token is not None or require_token:
            validation = validate_token(token, operation="shadow_execution")
            if not validation.valid:
                execution = self._refused_execution(
                    symbol=symbol,
                    bias=bias,
                    start_time=start_time,
                    reason=validation.reason,
                )
                self._update_metrics(execution)
                self.execution_history.append(execution)
                return execution
        
        # A: Adapt market data via Minkowski bridge
        market_state = self.market_adapter.adapt(ohlcv_data)
        market_state["session"] = session
        market_state["bias"] = bias
        market_state["symbol"] = symbol
        
        # B: Compute Hamiltonian from 18 operators
        hamiltonian = self.operators.get_hamiltonian(market_state, {})
        
        # C: Generate trajectory family
        initial_state = {
            "price": market_state.get("close", 100.0),
            "velocity": 0.0,
            "timestamp": time.time()
        }
        
        path_result = self.path_engine.execute_path_integral(
            initial_state, hamiltonian, self.operators
        )
        
        # D-F: Execute canonical cycle through apex engine
        proposal = {
            "symbol": symbol,
            "bias": bias,
            "session": session,
            "hamiltonian": hamiltonian
        }
        
        result = self.apex.execute_canonical_cycle(
            proposal=proposal,
            market_state=market_state,
            path_integral_result=path_result,
            mode=ExecutionMode.SHADOW
        )
        
        # Extract operator scores
        op_scores = self.operators.get_all_scores(market_state, {})
        
        # Create shadow execution record
        execution = ShadowExecution(
            execution_id=f"shadow_{symbol}_{int(time.time())}",
            timestamp=time.time(),
            symbol=symbol,
            bias=bias,
            outcome=result.outcome,
            trajectory=result.trajectory,
            evidence_hash=result.evidence_hash,
            operator_scores=op_scores,
            pnl_prediction=result.trajectory.get("predicted_pnl", 0) if result.trajectory else 0,
            execution_time_ms=result.execution_time_ms
        )

        append_execution_evidence(
            event_type="shadow_execution",
            execution_id=execution.execution_id,
            operation="shadow_execution",
            symbol=symbol,
            outcome=execution.outcome.value,
            token_status="authorized" if token is not None else "compatibility_mode",
            evidence_hash=execution.evidence_hash,
            payload={
                "bias": bias,
                "session": session,
                "pnl_prediction": execution.pnl_prediction,
                "execution_time_ms": execution.execution_time_ms,
            },
        )
        
        # Update metrics
        self._update_metrics(execution)
        self.execution_history.append(execution)
        
        return execution

    def _refused_execution(
        self,
        symbol: str,
        bias: str,
        start_time: float,
        reason: str,
    ) -> ShadowExecution:
        """Create an evidenced refusal when execution authority is missing."""
        evidence_hash = hashlib.sha256(
            f"SHADOW_REFUSED:{symbol}:{bias}:{reason}:{start_time}".encode()
        ).hexdigest()
        execution = ShadowExecution(
            execution_id=f"shadow_refused_{symbol}_{int(time.time())}",
            timestamp=time.time(),
            symbol=symbol,
            bias=bias,
            outcome=ExecutionOutcome.REFUSED,
            trajectory=None,
            evidence_hash=evidence_hash,
            operator_scores={},
            pnl_prediction=0.0,
            execution_time_ms=(time.time() - start_time) * 1000,
        )
        append_execution_evidence(
            event_type="shadow_refusal",
            execution_id=execution.execution_id,
            operation="shadow_execution",
            symbol=symbol,
            outcome=execution.outcome.value,
            token_status=reason,
            evidence_hash=evidence_hash,
            payload={"bias": bias, "reason": reason},
        )
        return execution
    
    def _update_metrics(self, execution: ShadowExecution):
        """Update performance metrics"""
        self.performance_metrics["total_executions"] += 1
        
        if execution.outcome == ExecutionOutcome.REFUSED:
            self.performance_metrics["refusals"] += 1
        elif execution.outcome == ExecutionOutcome.SUCCESS:
            self.performance_metrics["successes"] += 1
        
        # Running average execution time
        n = self.performance_metrics["total_executions"]
        old_avg = self.performance_metrics["avg_execution_time_ms"]
        self.performance_metrics["avg_execution_time_ms"] = (
            (old_avg * (n - 1) + execution.execution_time_ms) / n
        )
        
        # Cumulative PnL (simulated)
        self.performance_metrics["cumulative_pnl"] += execution.pnl_prediction
    
    def detect_drift(self,
                    shadow_exec: ShadowExecution,
                    hypothetical_live_pnl: float) -> DriftReport:
        """
        Detect drift between shadow prediction and hypothetical live result.
        
        In production, this compares shadow predictions against actual
        broker execution results.
        """
        divergence = abs(shadow_exec.pnl_prediction - hypothetical_live_pnl)
        threshold = 0.05  # 5% divergence threshold
        
        report = DriftReport(
            shadow_execution=shadow_exec.execution_id,
            hypothetical_live_result=hypothetical_live_pnl,
            divergence=divergence,
            threshold=threshold,
            triggered=divergence > threshold
        )
        
        self.drift_reports.append(report)
        return report
    
    def get_shadow_report(self) -> Dict[str, Any]:
        """Generate comprehensive shadow execution report"""
        return {
            "performance": self.performance_metrics,
            "recent_executions": [
                {
                    "id": e.execution_id,
                    "symbol": e.symbol,
                    "bias": e.bias,
                    "outcome": e.outcome.value,
                    "pnl_pred": round(e.pnl_prediction, 4),
                    "time_ms": round(e.execution_time_ms, 2)
                }
                for e in self.execution_history[-10:]
            ],
            "drift_alerts": [
                {
                    "execution": r.shadow_execution,
                    "divergence": round(r.divergence, 4),
                    "triggered": r.triggered
                }
                for r in self.drift_reports[-5:]
            ],
            "system_status": self.apex.get_engine_status()
        }
    
    def run_batch_shadow(self,
                        setups: List[Dict]) -> List[ShadowExecution]:
        """
        Execute multiple shadow trades in batch.
        
        Args:
            setups: List of {symbol, ohlcv, bias, session}
        
        Returns:
            List of ShadowExecution records
        """
        results = []
        for setup in setups:
            execution = self.execute_shadow(
                symbol=setup["symbol"],
                ohlcv_data=setup["ohlcv"],
                bias=setup.get("bias", "neutral"),
                session=setup.get("session", "neutral")
            )
            results.append(execution)
        return results
    
    def analyze_setup(self,
                     symbol: str,
                     ohlcv_data: List[Dict]) -> Dict[str, Any]:
        """
        Analyze trading setup without full execution.
        Returns operator scores and setup quality metrics.
        """
        market_state = self.market_adapter.adapt(ohlcv_data)
        
        # Get all 18 operator scores
        scores = self.operators.get_all_scores(market_state, {})
        
        # Compute setup quality
        potential_ops = [scores.get(k, 0) for k in [
            "kinetic", "liquidity_pool", "order_block", "fvg",
            "price_delivery", "sweep", "displacement", "ote"
        ]]
        
        projector_ops = [scores.get(k, 0) for k in [
            "session", "risk", "regime", "sailing_lane"
        ]]
        
        setup_quality = {
            "potential_strength": np.mean(potential_ops) if potential_ops else 0,
            "constraint_clearance": np.mean(projector_ops) if projector_ops else 0,
            "top_signals": sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5],
            "risk_flags": [k for k, v in scores.items() if v == 0 and "risk" in k]
        }
        
        return {
            "symbol": symbol,
            "operator_scores": scores,
            "setup_quality": setup_quality,
            "recommendation": "proceed" if setup_quality["potential_strength"] > 0.6 else "wait"
        }
