"""
Trading-TAEP Bridge

Converts trading system state to TAEP state and back.
"""

import numpy as np
import time
from typing import Dict, Optional

# TAEP imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from taep.core.state import TAEPState, ExecutionToken
from taep.chaos.three_body import ThreeBodyEngine


class TradingTAEPBridge:
    """
    Bridge between trading system and TAEP governance.
    
    Maps:
    - Market data → TAEP geometric state (q)
    - Price momentum → TAEP momentum (p)
    - Decision entropy → TAEP entropy (σ)
    - Execution auth → TAEP token (τ)
    """
    
    def __init__(self, three_body_engine: Optional[ThreeBodyEngine] = None):
        """
        Initialize bridge.
        
        Args:
            three_body_engine: Optional pre-configured engine
        """
        self.three_body = three_body_engine or ThreeBodyEngine()
    
    def trading_to_taep(
        self,
        market_state: Dict,
        geometry_data: Dict,
        decision_context: Dict,
        operation: str = 'TRADE_EXECUTION',
        budget: float = 1000.0
    ) -> TAEPState:
        """
        Convert trading state to TAEP state.
        
        Mapping:
        - q: [price, time, liquidity_field] - geometric
        - p: [velocity, acceleration, spread] - momentum
        - k: chaotic key from three-body
        - π: trading constraints
        - σ: decision entropy
        - τ: execution token
        """
        # Extract market data
        price = market_state.get('mid', market_state.get('price', 1.0))
        timestamp = decision_context.get('timestamp', time.time())
        phi = geometry_data.get('phi', 0.0)
        
        # Geometric state (q)
        q = np.array([float(price), float(timestamp), float(phi)])
        
        # Momentum (p) from microstructure
        velocity = market_state.get('velocity', 0.0)
        acceleration = market_state.get('acceleration', 0.0)
        spread = market_state.get('spread', 0.0)
        p = np.array([float(velocity), float(acceleration), float(spread)])
        
        # Chaotic key (k) from three-body
        k = self.three_body.generate_key_seed(q, p)
        if len(k) < 3:
            k = np.pad(k, (0, 3 - len(k)), mode='constant')
        k = k[:3]  # Ensure 3-dimensional
        
        # Policy (π) from trading constraints
        policy = {
            'max_position': decision_context.get('max_position', 1.0),
            'session': decision_context.get('session', 'london'),
            'risk_budget': decision_context.get('risk_budget', budget),
            'symbol': decision_context.get('symbol', 'EURUSD'),
        }
        
        # Entropy (σ) from action functional
        action_scores = decision_context.get('action_scores', {})
        entropy = self._compute_decision_entropy(action_scores)
        
        # Token (τ)
        token = ExecutionToken(
            operation=operation,
            budget=float(budget),
            expiry=time.time() + 300  # 5 minutes
        )
        
        return TAEPState(
            q=q,
            p=p,
            k=k,
            policy=policy,
            entropy=entropy,
            token=token
        )
    
    def taep_to_trading_decision(
        self,
        taep_state: TAEPState,
        authorized: bool
    ) -> Dict:
        """
        Convert TAEP state back to trading decision.
        
        Returns decision dict with TAEP governance info.
        """
        return {
            'authorized': authorized,
            'price': float(taep_state.q[0]),
            'timestamp': float(taep_state.q[1]),
            'liquidity_field': float(taep_state.q[2]),
            'entropy': float(taep_state.entropy),
            'taep_state_id': taep_state.state_id,
            'token_budget_remaining': taep_state.token.budget if taep_state.token else 0.0,
        }
    
    def _compute_decision_entropy(self, action_scores: Dict) -> float:
        """
        Compute decision entropy from action scores.
        
        Higher entropy = more uncertain decision.
        """
        if not action_scores:
            return 0.5  # Neutral entropy
        
        # Normalize scores to probabilities
        scores = np.array(list(action_scores.values()))
        if np.sum(scores) == 0:
            return 0.5
        
        probs = scores / np.sum(scores)
        
        # Shannon entropy: H = -Σ p log p
        entropy = -np.sum(probs * np.log(probs + 1e-10))
        
        # Normalize to [0, 1]
        max_entropy = np.log(len(probs)) if len(probs) > 1 else 1.0
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        
        return float(normalized_entropy)


# Global bridge instance
default_bridge = TradingTAEPBridge()


def quick_convert(
    market_state: Dict,
    geometry_data: Dict,
    decision_context: Dict
) -> TAEPState:
    """Quick conversion using default bridge."""
    return default_bridge.trading_to_taep(
        market_state, geometry_data, decision_context
    )
