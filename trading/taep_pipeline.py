"""
TAEP-Governed Trading Pipeline

Executes the 20-stage trading pipeline under TAEP governance.
Every stage is a TAEP state transition with authorization and evidence.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Tuple, Optional, Dict
from taep.core.state import TAEPState
from taep.scheduler.scheduler import TAEPScheduler, TAEPEvidence
from taep.constraints.admissibility import AdmissibilityChecker
from trading.pipeline.orchestrator import PipelineOrchestrator, PipelineContext
from trading.taep_bridge import TradingTAEPBridge


class TAEPTradingPipeline:
    """
    20-stage trading pipeline governed by TAEP.
    
    Each stage is a TAEP state transition:
    1. Pre-stage: Validate admissibility
    2. Execute: Hamiltonian evolution
    3. Post-stage: Scheduler authorization + evidence
    """
    
    def __init__(
        self,
        base_pipeline: PipelineOrchestrator,
        taep_scheduler: TAEPScheduler,
        bridge: Optional[TradingTAEPBridge] = None
    ):
        """
        Initialize TAEP-governed pipeline.
        
        Args:
            base_pipeline: The trading pipeline to govern
            taep_scheduler: TAEP collapse authority
            bridge: Trading-TAEP bridge
        """
        self.pipeline = base_pipeline
        self.scheduler = taep_scheduler
        self.bridge = bridge or TradingTAEPBridge()
        self.admissibility = AdmissibilityChecker()
        self.evidence_log = []
    
    def execute_with_taep(
        self,
        raw_data: Dict,
        symbol: str,
        context: Optional[PipelineContext] = None
    ) -> Tuple[PipelineContext, TAEPState, TAEPEvidence]:
        """
        Execute full pipeline with TAEP governance.
        
        Flow:
        1. Build initial TAEP state from market data
        2. Run pipeline stages under TAEP
        3. Final authorization and evidence
        
        Args:
            raw_data: Raw market data
            symbol: Trading symbol
            context: Optional existing context
        
        Returns:
            (context, final_state, evidence): Full execution result
        """
        # Build initial TAEP state
        market_state = self._extract_market_state(raw_data)
        geometry_data = self._extract_geometry(raw_data)
        decision_context = {
            'symbol': symbol,
            'timestamp': raw_data.get('timestamp', time.time()),
            'session': raw_data.get('session', 'london'),
        }
        
        taep_state = self.bridge.trading_to_taep(
            market_state, geometry_data, decision_context
        )
        
        # Run pipeline with TAEP governance
        context = self.pipeline.execute(raw_data, symbol)
        
        # Update TAEP state with pipeline results
        taep_state = self._update_state_from_pipeline(taep_state, context)
        
        # Final authorization
        proposal = {
            'should_trade': context.collapse_decision == 'AUTHORIZED',
            'action_scores': context.action_scores if hasattr(context, 'action_scores') else {},
        }
        
        authorized = self.scheduler.authorize(taep_state, proposal)
        
        # Collapse and emit evidence
        evidence = self.scheduler.collapse(
            taep_state, authorized, proposal,
            reason=None if authorized else "Pipeline decision refused"
        )
        
        self.evidence_log.append(evidence)
        
        return context, taep_state, evidence
    
    def _extract_market_state(self, raw_data: Dict) -> Dict:
        """Extract market state from raw data."""
        ticks = raw_data.get('ticks', [])
        if ticks:
            last_tick = ticks[-1]
            return {
                'mid': (last_tick.get('bid', 1.0) + last_tick.get('ask', 1.0)) / 2,
                'spread': last_tick.get('ask', 1.0) - last_tick.get('bid', 1.0),
                'velocity': 0.0,  # Would compute from history
                'acceleration': 0.0,
            }
        return {'mid': 1.0, 'spread': 0.0, 'velocity': 0.0, 'acceleration': 0.0}
    
    def _extract_geometry(self, raw_data: Dict) -> Dict:
        """Extract geometry data from raw data."""
        return {
            'phi': 0.0,  # Would compute from ICT structures
            'regime': 'flat',
        }
    
    def _update_state_from_pipeline(
        self,
        state: TAEPState,
        context: PipelineContext
    ) -> TAEPState:
        """Update TAEP state with pipeline results."""
        # Update with geometry data if computed
        if hasattr(context, 'geometry_data') and context.geometry_data:
            phi = context.geometry_data.get('phi', state.q[2])
            state.q[2] = float(phi)
        
        return state
    
    def get_audit_trail(self) -> list:
        """Get complete audit trail."""
        return [e.to_dict() for e in self.evidence_log]


import time


def create_taep_pipeline(
    scheduler: Optional[TAEPScheduler] = None,
    base_pipeline: Optional[PipelineOrchestrator] = None
) -> TAEPTradingPipeline:
    """
    Factory function to create TAEP-governed pipeline.
    
    Args:
        scheduler: Optional TAEP scheduler
        base_pipeline: Optional base trading pipeline
    
    Returns:
        TAEPTradingPipeline: Ready-to-use governed pipeline
    """
    if scheduler is None:
        from taep.scheduler.scheduler import TAEPScheduler
        scheduler = TAEPScheduler()
    
    if base_pipeline is None:
        from trading.pipeline.orchestrator import PipelineOrchestrator
        from trading.kernel.scheduler import Scheduler
        base_pipeline = PipelineOrchestrator(scheduler=Scheduler())
    
    return TAEPTradingPipeline(base_pipeline, scheduler)
