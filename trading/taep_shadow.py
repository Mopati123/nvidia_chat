"""
TAEP Shadow Mode

Shadow trading with full TAEP governance and audit trail.
Decisions are logged but not executed - for ML training.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from taep.core.state import TAEPState
from taep.scheduler.scheduler import TAEPScheduler, TAEPEvidence
from taep.audit.evidence_writer import EvidenceWriter
from trading.taep_bridge import TradingTAEPBridge
from trading.taep_pipeline import TAEPTradingPipeline


@dataclass
class ShadowDecisionContext:
    """Complete context for a shadow decision with TAEP."""
    
    timestamp: float
    decision_id: str
    
    # Market state
    market_state: Dict
    
    # ICT geometry
    ict_structures: Dict
    
    # Riemannian geometry
    geometry_data: Dict
    
    # TAEP state
    taep_state: Dict
    
    # TAEP evidence
    taep_evidence: Dict
    
    # Decision
    authorized: bool
    should_trade: bool
    
    # Simulated outcome
    predicted_pnl: float
    predicted_outcome: str
    
    # Actual outcome (if available later)
    actual_pnl: Optional[float] = None
    actual_outcome: Optional[str] = None


class TAEPShadowOrchestrator:
    """
    Shadow mode execution with full TAEP governance.
    
    Every decision is:
    1. TAEP state transition
    2. Scheduler-authorized (or refused)
    3. Audited with evidence
    4. Used for ML training
    """
    
    def __init__(
        self,
        taep_pipeline: TAEPTradingPipeline,
        bridge: Optional[TradingTAEPBridge] = None,
        evidence_writer: Optional[EvidenceWriter] = None
    ):
        """
        Initialize shadow orchestrator.
        
        Args:
            taep_pipeline: TAEP-governed trading pipeline
            bridge: Trading-TAEP bridge
            evidence_writer: Evidence persistence
        """
        self.pipeline = taep_pipeline
        self.bridge = bridge or TradingTAEPBridge()
        self.evidence_writer = evidence_writer or EvidenceWriter('taep_shadow_audit.log')
        
        self.decisions: List[ShadowDecisionContext] = []
        self.metrics = {
            'total_decisions': 0,
            'authorized': 0,
            'refused': 0,
            'predicted_positive_pnl': 0,
            'predicted_negative_pnl': 0,
        }
    
    def run_shadow_decision(
        self,
        market_data: Dict,
        symbol: str = 'EURUSD'
    ) -> Tuple[ShadowDecisionContext, TAEPEvidence]:
        """
        Execute single shadow decision with full TAEP governance.
        
        Args:
            market_data: Market tick/OHLCV data
            symbol: Trading symbol
        
        Returns:
            (shadow_ctx, evidence): Decision context and TAEP evidence
        """
        # Extract data
        ict_structures = market_data.get('ict_structures', {})
        
        # Build TAEP state
        market_state = self._extract_market_state(market_data)
        geometry_data = self._extract_geometry(market_data)
        decision_context = {
            'symbol': symbol,
            'timestamp': market_data.get('timestamp', time.time()),
            'session': market_data.get('session', 'london'),
        }
        
        taep_state = self.bridge.trading_to_taep(
            market_state, geometry_data, decision_context
        )
        
        # Execute pipeline
        try:
            context, final_state, evidence = self.pipeline.execute_with_taep(
                market_data, symbol
            )
            authorized = evidence.decision == 'ACCEPT'
            should_trade = authorized and context.collapse_decision == 'AUTHORIZED'
        except Exception as e:
            # Pipeline error - refuse
            authorized = False
            should_trade = False
            evidence = self._create_error_evidence(taep_state, str(e))
        
        # Simulate outcome
        predicted_pnl = self._simulate_outcome(final_state, should_trade)
        
        # Create shadow context
        shadow_ctx = ShadowDecisionContext(
            timestamp=time.time(),
            decision_id=evidence.evidence_id,
            market_state=market_state,
            ict_structures=ict_structures,
            geometry_data=geometry_data,
            taep_state=final_state.to_dict(),
            taep_evidence=evidence.to_dict(),
            authorized=authorized,
            should_trade=should_trade,
            predicted_pnl=predicted_pnl,
            predicted_outcome='win' if predicted_pnl > 0 else 'loss',
        )
        
        # Log decision
        self.decisions.append(shadow_ctx)
        self._update_metrics(shadow_ctx)
        
        # Write evidence to persistent storage
        self.evidence_writer.write_evidence(evidence)
        
        return shadow_ctx, evidence
    
    def run_shadow_session(
        self,
        market_data_stream: List[Dict],
        symbol: str = 'EURUSD'
    ) -> List[ShadowDecisionContext]:
        """
        Run shadow session over multiple ticks.
        
        Args:
            market_data_stream: List of market data snapshots
            symbol: Trading symbol
        
        Returns:
            List of decision contexts
        """
        results = []
        
        for market_data in market_data_stream:
            ctx, _ = self.run_shadow_decision(market_data, symbol)
            results.append(ctx)
        
        return results
    
    def _extract_market_state(self, market_data: Dict) -> Dict:
        """Extract market state from data."""
        ticks = market_data.get('ticks', [])
        if ticks:
            last = ticks[-1]
            return {
                'mid': (last.get('bid', 1.0) + last.get('ask', 1.0)) / 2,
                'spread': last.get('ask', 1.0) - last.get('bid', 1.0),
                'velocity': 0.0,
                'acceleration': 0.0,
            }
        return {'mid': 1.0, 'spread': 0.0, 'velocity': 0.0, 'acceleration': 0.0}
    
    def _extract_geometry(self, market_data: Dict) -> Dict:
        """Extract geometry from data."""
        return {
            'phi': 0.0,
            'regime': 'flat',
            'curvature_K': 0.0,
        }
    
    def _simulate_outcome(self, taep_state: TAEPState, should_trade: bool) -> float:
        """
        Simulate trade outcome based on TAEP state.
        
        Simple model: outcome depends on entropy and chaos.
        """
        if not should_trade:
            return 0.0
        
        # Use TAEP state to predict outcome
        # Higher entropy = more uncertain outcome
        entropy = taep_state.entropy
        key_magnitude = np.mean(np.abs(taep_state.k))
        
        # Simulate PnL based on state
        base_pnl = np.random.randn() * 10  # Random around 0
        entropy_effect = (entropy - 0.5) * 5  # Higher entropy = less predictable
        
        return base_pnl + entropy_effect
    
    def _create_error_evidence(self, state: TAEPState, error: str) -> TAEPEvidence:
        """Create evidence for pipeline error."""
        from taep.scheduler.scheduler import TAEPScheduler
        scheduler = TAEPScheduler()
        return scheduler.collapse(state, authorized=False, reason=f"Pipeline error: {error}")
    
    def _update_metrics(self, ctx: ShadowDecisionContext):
        """Update metrics from decision."""
        self.metrics['total_decisions'] += 1
        
        if ctx.authorized:
            self.metrics['authorized'] += 1
        else:
            self.metrics['refused'] += 1
        
        if ctx.predicted_pnl > 0:
            self.metrics['predicted_positive_pnl'] += 1
        else:
            self.metrics['predicted_negative_pnl'] += 1
    
    def get_ml_training_data(self) -> List[Dict]:
        """
        Get training data for ML.
        
        Returns labeled examples:
        - Features: TAEP state components
        - Label: 1 if predicted PnL > 0, else 0
        """
        training_data = []
        
        for ctx in self.decisions:
            features = {
                'entropy': ctx.taep_state.get('entropy', 0.5),
                'key_magnitude': float(np.mean(np.abs(ctx.taep_state.get('k', [0])))),
                'price': ctx.market_state.get('mid', 1.0),
                'velocity': ctx.market_state.get('velocity', 0.0),
            }
            
            label = 1 if ctx.predicted_pnl > 0 else 0
            
            training_data.append({
                'features': features,
                'label': label,
                'decision_id': ctx.decision_id,
            })
        
        return training_data
    
    def get_statistics(self) -> Dict:
        """Get shadow mode statistics."""
        if not self.decisions:
            return self.metrics
        
        return {
            **self.metrics,
            'authorization_rate': self.metrics['authorized'] / max(1, self.metrics['total_decisions']),
            'avg_predicted_pnl': sum(d.predicted_pnl for d in self.decisions) / len(self.decisions),
        }


import numpy as np


def create_shadow_orchestrator(
    pipeline: Optional[TAEPTradingPipeline] = None
) -> TAEPShadowOrchestrator:
    """Factory function."""
    if pipeline is None:
        from trading.taep_pipeline import create_taep_pipeline
        pipeline = create_taep_pipeline()
    
    return TAEPShadowOrchestrator(pipeline)
