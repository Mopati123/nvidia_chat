"""
Shadow Mode Runner

Runs the trading system in shadow mode - making all decisions
but not executing them. Logs what *would* have happened for validation.

Useful for:
- Live system validation without risk
- A/B testing new strategies
- Performance tracking vs actual market
"""

import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging

import numpy as np

from .paper_broker import PaperBroker, Order, OrderSide, ExecutionResult

logger = logging.getLogger(__name__)


@dataclass
class ShadowDecision:
    """
    Record of a shadow decision.
    
    Tracks what the system decided and what would have happened.
    """
    timestamp: str
    market_data: Dict
    system_decision: Dict
    selected_trajectory: int
    confidence: float
    should_trade: bool
    refused: bool
    refusal_reason: Optional[str]
    predicted_outcome: Optional[float] = None  # Predicted PnL
    actual_outcome: Optional[float] = None  # Filled in later
    metadata: Dict = field(default_factory=dict)


class ShadowModeRunner:
    """
    Run trading system in shadow mode for validation.
    
    Makes all decisions, logs them, but doesn't execute trades.
    Optionally runs paper trading for simulated fills.
    """
    
    def __init__(
        self,
        trading_system,  # The full trading system
        paper_broker: Optional[PaperBroker] = None,
        log_decisions: bool = True,
        mode: str = "shadow"  # "shadow" or "paper"
    ):
        self.trading_system = trading_system
        self.paper_broker = paper_broker
        self.log_decisions = log_decisions
        self.mode = mode
        
        # Decision log
        self.decision_log: List[ShadowDecision] = []
        self.execution_log: List[ExecutionResult] = []
        
        # Statistics
        self.total_decisions = 0
        self.trade_decisions = 0
        self.refused_decisions = 0
        
        logger.info(f"ShadowModeRunner initialized in {mode} mode")
    
    def run_decision_cycle(
        self,
        market_data: Dict,
        context: Optional[Dict] = None
    ) -> ShadowDecision:
        """
        Run one decision cycle and log the result.
        
        Args:
            market_data: Current market data dict
            context: Optional additional context
        
        Returns:
            ShadowDecision with full decision record
        """
        start_time = time.perf_counter()
        
        # Get system decision
        try:
            system_result = self.trading_system.decide(market_data, context)
            
            should_trade = system_result.get('should_trade', False)
            refused = system_result.get('refused', not should_trade)
            refusal_reason = system_result.get('refusal_reason')
            
        except Exception as e:
            logger.error(f"System decision failed: {e}")
            should_trade = False
            refused = True
            refusal_reason = f"Error: {e}"
            system_result = {'error': str(e)}
        
        # Build shadow decision
        decision = ShadowDecision(
            timestamp=datetime.now().isoformat(),
            market_data=market_data.copy(),
            system_decision=system_result,
            selected_trajectory=system_result.get('selected_trajectory', 0),
            confidence=system_result.get('confidence', 0.0),
            should_trade=should_trade,
            refused=refused,
            refusal_reason=refusal_reason,
            metadata={
                'decision_time_ms': (time.perf_counter() - start_time) * 1000
            }
        )
        
        # Log decision
        if self.log_decisions:
            self.decision_log.append(decision)
        
        # Update statistics
        self.total_decisions += 1
        if should_trade:
            self.trade_decisions += 1
        else:
            self.refused_decisions += 1
        
        # Paper trading execution (optional)
        if self.mode == "paper" and should_trade and self.paper_broker:
            execution = self._execute_paper_trade(decision, market_data)
            if execution:
                self.execution_log.append(execution)
        
        logger.debug(
            f"Decision cycle: trade={should_trade}, "
            f"conf={decision.confidence:.2f}, "
            f"time={decision.metadata['decision_time_ms']:.1f}ms"
        )
        
        return decision
    
    def _execute_paper_trade(
        self,
        decision: ShadowDecision,
        market_data: Dict
    ) -> Optional[ExecutionResult]:
        """Execute paper trade based on decision"""
        if not self.paper_broker:
            return None
        
        # Extract trade details from decision
        symbol = market_data.get('symbol', 'UNKNOWN')
        side_str = decision.system_decision.get('side', 'buy')
        side = OrderSide.BUY if side_str.lower() == 'buy' else OrderSide.SELL
        size = decision.system_decision.get('size', 0.01)
        current_price = market_data.get('current_price', market_data.get('close', 1.0))
        
        # Create order
        order = Order(
            symbol=symbol,
            side=side,
            size=size,
            stop_loss=decision.system_decision.get('stop_loss'),
            take_profit=decision.system_decision.get('take_profit')
        )
        
        # Execute
        result = self.paper_broker.execute_market_order(order, current_price)
        
        return result
    
    def update_actual_outcomes(self, outcomes: Dict[str, float]):
        """
        Update decisions with actual market outcomes.
        
        Call this after market moves to validate predictions.
        
        Args:
            outcomes: Dict mapping decision timestamp to actual PnL
        """
        for decision in self.decision_log:
            if decision.timestamp in outcomes:
                decision.actual_outcome = outcomes[decision.timestamp]
                
                # Calculate prediction error
                if decision.predicted_outcome is not None:
                    error = abs(decision.predicted_outcome - decision.actual_outcome)
                    decision.metadata['prediction_error'] = error
    
    def get_shadow_statistics(self) -> Dict:
        """Get statistics about shadow decisions"""
        if not self.decision_log:
            return {
                'total_decisions': 0,
                'trade_rate': 0,
                'refusal_rate': 0,
                'avg_confidence': 0
            }
        
        confidences = [d.confidence for d in self.decision_log if d.should_trade]
        
        return {
            'total_decisions': self.total_decisions,
            'trade_decisions': self.trade_decisions,
            'refused_decisions': self.refused_decisions,
            'trade_rate': self.trade_decisions / self.total_decisions if self.total_decisions > 0 else 0,
            'refusal_rate': self.refused_decisions / self.total_decisions if self.total_decisions > 0 else 0,
            'avg_confidence': sum(confidences) / len(confidences) if confidences else 0,
            'decision_log_size': len(self.decision_log)
        }
    
    def get_validation_report(self) -> str:
        """
        Generate validation report comparing predictions vs actuals.
        """
        stats = self.get_shadow_statistics()
        
        # Calculate prediction accuracy
        comparison_decisions = [
            d for d in self.decision_log 
            if d.predicted_outcome is not None and d.actual_outcome is not None
        ]
        
        if comparison_decisions:
            errors = [
                abs(d.predicted_outcome - d.actual_outcome) 
                for d in comparison_decisions
            ]
            avg_error = sum(errors) / len(errors)
            
            directional_accuracy = sum(
                1 for d in comparison_decisions
                if (d.predicted_outcome > 0) == (d.actual_outcome > 0)
            ) / len(comparison_decisions)
        else:
            avg_error = None
            directional_accuracy = None
        
        report = f"""
═══════════════════════════════════════════════════════════
                SHADOW MODE VALIDATION REPORT
═══════════════════════════════════════════════════════════

Decision Statistics:
  Total Decisions: {stats['total_decisions']}
  Trade Decisions: {stats['trade_decisions']} ({stats['trade_rate']:.1%})
  Refused Decisions: {stats['refused_decisions']} ({stats['refusal_rate']:.1%})
  Average Confidence: {stats['avg_confidence']:.2f}

Prediction Accuracy:
  Decisions with Outcomes: {len(comparison_decisions)}
  Average Prediction Error: {avg_error if avg_error is not None else 'N/A'}
  Directional Accuracy: {f"{directional_accuracy:.1%}" if directional_accuracy is not None else 'N/A'}

Mode: {self.mode.upper()}
"""
        
        if self.mode == "paper" and self.paper_broker:
            report += f"\n{self.paper_broker.get_trade_report()}"
        
        return report
    
    def export_decision_log(self, filepath: str):
        """Export decision log to JSON file"""
        import json
        
        data = [
            {
                'timestamp': d.timestamp,
                'should_trade': d.should_trade,
                'refused': d.refused,
                'refusal_reason': d.refusal_reason,
                'confidence': d.confidence,
                'selected_trajectory': d.selected_trajectory,
                'predicted_outcome': d.predicted_outcome,
                'actual_outcome': d.actual_outcome,
                'metadata': d.metadata
            }
            for d in self.decision_log
        ]
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(data)} decisions to {filepath}")


class LiveShadowComparator:
    """
    Compare shadow decisions against live execution.
    
    Useful for:
    - Validating that shadow matches live
    - Detecting execution slippage
    - Measuring real-world vs simulated performance
    """
    
    def __init__(self):
        self.shadow_decisions: List[ShadowDecision] = []
        self.live_trades: List[Dict] = []
        self.comparisons: List[Dict] = []
    
    def add_shadow_decision(self, decision: ShadowDecision):
        """Record a shadow decision"""
        self.shadow_decisions.append(decision)
    
    def add_live_trade(self, trade: Dict):
        """Record a live trade execution"""
        self.live_trades.append(trade)
        self._compare_latest()
    
    def _compare_latest(self):
        """Compare latest shadow decision with live trade"""
        if not self.shadow_decisions or not self.live_trades:
            return
        
        shadow = self.shadow_decisions[-1]
        live = self.live_trades[-1]
        
        comparison = {
            'timestamp': datetime.now().isoformat(),
            'shadow_would_trade': shadow.should_trade,
            'live_did_trade': live.get('executed', False),
            'shadow_confidence': shadow.confidence,
            'shadow_refusal': shadow.refused,
            'shadow_refusal_reason': shadow.refusal_reason,
            'live_slippage': live.get('slippage', 0),
            'agreement': shadow.should_trade == live.get('executed', False)
        }
        
        self.comparisons.append(comparison)
    
    def get_agreement_rate(self) -> float:
        """Calculate agreement rate between shadow and live"""
        if not self.comparisons:
            return 0.0
        
        agreements = sum(1 for c in self.comparisons if c['agreement'])
        return agreements / len(self.comparisons)
    
    def get_comparison_report(self) -> str:
        """Generate comparison report"""
        agreement_rate = self.get_agreement_rate()
        
        report = f"""
═══════════════════════════════════════════════════════════
            SHADOW vs LIVE COMPARISON REPORT
═══════════════════════════════════════════════════════════

Comparison Statistics:
  Total Comparisons: {len(self.comparisons)}
  Agreement Rate: {agreement_rate:.1%}
  Shadow Decisions: {len(self.shadow_decisions)}
  Live Trades: {len(self.live_trades)}

Discrepancy Analysis:
  Shadow Trade / Live No Trade: {sum(1 for c in self.comparisons if c['shadow_would_trade'] and not c['live_did_trade'])}
  Shadow No Trade / Live Trade: {sum(1 for c in self.comparisons if not c['shadow_would_trade'] and c['live_did_trade'])}

Average Live Slippage: {np.mean([c['live_slippage'] for c in self.comparisons if c['live_slippage']]):.4%}
═══════════════════════════════════════════════════════════
"""
        return report
