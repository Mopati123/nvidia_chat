"""
weight_update_operator.py - Backward-law weight adaptation.

Implements the core learning equation:

    w_{t+1} = Π_simplex(w_t + η · ∇_w J)

Where:
    J = α·PnL_norm + β·ΔS - γ·MismatchPenalty (reward signal)
    ∇_w J ≈ feature attribution via path contributions
    Π_simplex = projection onto probability simplex

Governance constraints:
    - Only updates if Π_total passed (constraints_passed)
    - Only updates if Λ authorized (collapse_authorized)
    - Only updates if ℰ complete (evidence_complete)

This operator lives in the kernel and executes post-reconciliation,
ensuring weight updates are audit-gated and lawful.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ReconciliationStatus(Enum):
    """Reconciliation outcome states"""
    MATCH = "match"
    MISMATCH = "mismatch"
    ROLLBACK = "rollback"


@dataclass
class WeightUpdateResult:
    """Result of weight update operation"""
    old_weights: Dict[str, float]
    new_weights: Dict[str, float]
    reward: float
    pnl: float
    delta_s: float
    status: str
    updated: bool
    reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for evidence logging"""
        return {
            'old_weights': self.old_weights,
            'new_weights': self.new_weights,
            'reward': self.reward,
            'pnl': self.pnl,
            'delta_s': self.delta_s,
            'status': self.status,
            'updated': self.updated,
            'reason': self.reason,
        }


class WeightUpdateOperator:
    """
    Weight update operator implementing the backward learning law.
    
    Post-collapse weight adaptation that reshapes the action landscape
    based on real-world outcomes while maintaining mathematical constraints.
    
    Key equation:
        w_new = Π_simplex(w_old + η · reward · normalized_contributions)
    
    Governance:
        - Updates only occur if all gates pass
        - Weight clamping prevents overfitting (0.05 to 0.8)
        - Slow learning (η ≤ 0.05) ensures stability
        - All updates produce evidence for audit
    """
    
    # Default hyperparameters from specification
    DEFAULT_PARAMS = {
        'alpha': 0.6,          # PnL weight in reward
        'beta': 0.3,           # ΔS weight in reward
        'gamma': 0.8,          # Mismatch penalty weight
        'eta': 0.05,           # Learning rate
        'weight_min': 0.05,    # Minimum weight (prevents elimination)
        'weight_max': 0.8,     # Maximum weight (prevents dominance)
    }
    
    # Component names for L/T/E/R structure
    COMPONENTS = ['L', 'T', 'E', 'R']  # Liquidity, Time, Entry, Risk
    
    def __init__(self, params: Optional[Dict] = None):
        """
        Initialize weight update operator.
        
        Args:
            params: Optional override for DEFAULT_PARAMS
        """
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self.update_history: List[WeightUpdateResult] = []
        
    def update(self,
             weights: Dict[str, float],
             contrib: Dict[str, float],
             pnl: float,
             delta_s: float,
             status: str,
             constraints_passed: bool = True,
             collapse_authorized: bool = True,
             evidence_complete: bool = True) -> WeightUpdateResult:
        """
        Execute weight update with full governance checks.
        
        Args:
            weights: Current weights dict (e.g., {'L': 0.5, 'T': 0.3, 'E': 0.1, 'R': 0.1})
            contrib: Feature contributions from selected path (e.g., {'L': 10.0, 'T': 5.0, ...})
            pnl: Realized profit/loss from trade
            delta_s: Entropy reduction (information gain)
            status: Reconciliation status ('match', 'mismatch', 'rollback')
            constraints_passed: Whether Π_total constraints were satisfied
            collapse_authorized: Whether Λ authorized the collapse
            evidence_complete: Whether ℰ evidence is complete
        
        Returns:
            WeightUpdateResult with old/new weights and update metadata
        """
        old_weights = weights.copy()
        
        # Step 0: Governance gate checks
        if not self._check_governance(constraints_passed, collapse_authorized, evidence_complete):
            return WeightUpdateResult(
                old_weights=old_weights,
                new_weights=old_weights,
                reward=0.0,
                pnl=pnl,
                delta_s=delta_s,
                status=status,
                updated=False,
                reason="Governance gate failed"
            )
        
        # Step 1: Compute mismatch penalty
        mismatch_penalty = self._compute_mismatch_penalty(status)
        
        # Step 2: Normalize PnL to [-1, 1]
        pnl_norm = self._normalize_pnl(pnl)
        
        # Step 3: Compute reward signal J
        reward = self._compute_reward(pnl_norm, delta_s, mismatch_penalty)
        
        # Step 4: Normalize contributions (feature attribution)
        norm_contrib = self._normalize_contributions(contrib)
        
        # Step 5: Update weights
        new_weights = self._update_weights(weights, reward, norm_contrib)
        
        # Step 6: Project onto simplex (maintain Σw = 1, w > 0)
        new_weights = self._project_simplex(new_weights)
        
        # Step 7: Clamp weights for stability
        new_weights = self._clamp_weights(new_weights)
        
        # Step 8: Re-normalize after clamping
        new_weights = self._project_simplex(new_weights)
        
        # Create result
        result = WeightUpdateResult(
            old_weights=old_weights,
            new_weights=new_weights,
            reward=reward,
            pnl=pnl,
            delta_s=delta_s,
            status=status,
            updated=True,
            reason="Weight update successful"
        )
        
        # Store history
        self.update_history.append(result)
        
        logger.info(f"Weight update: reward={reward:.4f}, L={new_weights.get('L', 0):.3f}, "
                   f"T={new_weights.get('T', 0):.3f}, E={new_weights.get('E', 0):.3f}, "
                   f"R={new_weights.get('R', 0):.3f}")
        
        return result
    
    def _check_governance(self, 
                         constraints_passed: bool,
                         collapse_authorized: bool,
                         evidence_complete: bool) -> bool:
        """
        Check governance constraints before allowing update.
        
        All three must be True:
            - Π_total: Constraints passed
            - Λ: Collapse authorized
            - ℰ: Evidence complete
        """
        if not constraints_passed:
            logger.warning("Weight update blocked: Π_total constraints not passed")
            return False
        
        if not collapse_authorized:
            logger.warning("Weight update blocked: Λ collapse not authorized")
            return False
        
        if not evidence_complete:
            logger.warning("Weight update blocked: ℰ evidence incomplete")
            return False
        
        return True
    
    def _compute_mismatch_penalty(self, status: str) -> float:
        """
        Compute penalty based on reconciliation status.
        
        match: 0.0 (no penalty)
        mismatch: 1.0 (heavy penalty)
        rollback: 2.0 (maximum penalty)
        """
        penalties = {
            'match': 0.0,
            'mismatch': 1.0,
            'rollback': 2.0,
        }
        return penalties.get(status, 1.0)
    
    def _normalize_pnl(self, pnl: float) -> float:
        """
        Normalize PnL to [-1, 1] range.
        
        Uses tanh-like compression to handle outliers.
        """
        # Soft normalization: pnl / (|pnl| + ε)
        epsilon = 1e-6
        return pnl / (abs(pnl) + epsilon)
    
    def _compute_reward(self, 
                       pnl_norm: float,
                       delta_s: float,
                       mismatch_penalty: float) -> float:
        """
        Compute reward signal J.
        
        J = α·PnL_norm + β·ΔS - γ·MismatchPenalty
        
        Where:
            α = 0.6 (PnL weight)
            β = 0.3 (entropy gain weight)
            γ = 0.8 (mismatch penalty weight)
        """
        alpha = self.params['alpha']
        beta = self.params['beta']
        gamma = self.params['gamma']
        
        reward = (
            alpha * pnl_norm +
            beta * delta_s -
            gamma * mismatch_penalty
        )
        
        return reward
    
    def _normalize_contributions(self, contrib: Dict[str, float]) -> Dict[str, float]:
        """
        Normalize feature contributions to sum to 1.
        
        This provides the attribution: how much each component
        (L, T, E, R) contributed to the selected path.
        """
        total = sum(contrib.values()) + 1e-8  # epsilon to prevent div by zero
        
        # Normalize
        norm = {k: v / total for k, v in contrib.items()}
        
        # Ensure all components exist
        for comp in self.COMPONENTS:
            if comp not in norm:
                norm[comp] = 0.0
        
        return norm
    
    def _update_weights(self,
                       weights: Dict[str, float],
                       reward: float,
                       norm_contrib: Dict[str, float]) -> Dict[str, float]:
        """
        Update weights using reward and normalized contributions.
        
        w_new = w_old + η · reward · normalized_contribution
        """
        eta = self.params['eta']
        
        new_weights = {}
        for component in self.COMPONENTS:
            old_w = weights.get(component, 0.25)  # Default to uniform
            contribution = norm_contrib.get(component, 0.25)
            
            # Update rule
            new_w = old_w + eta * reward * contribution
            new_weights[component] = new_w
        
        return new_weights
    
    def _project_simplex(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Project weights onto probability simplex.
        
        Ensures:
            Σw_i = 1 (normalized)
            w_i > 0 (positive)
        
        Algorithm:
            1. Set negative weights to 0
            2. Normalize to sum to 1
        """
        # Set negatives to 0
        positive_weights = {k: max(v, 0.0) for k, v in weights.items()}
        
        # Normalize
        total = sum(positive_weights.values())
        if total == 0:
            # Fallback to uniform if all zero
            n = len(self.COMPONENTS)
            return {comp: 1.0 / n for comp in self.COMPONENTS}
        
        normalized = {k: v / total for k, v in positive_weights.items()}
        
        return normalized
    
    def _clamp_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Clamp weights to prevent overfitting.
        
        Enforces:
            weight_min ≤ w_i ≤ weight_max
        
        Defaults:
            min = 0.05 (no component can be eliminated)
            max = 0.8 (no component can dominate)
        """
        w_min = self.params['weight_min']
        w_max = self.params['weight_max']
        
        clamped = {
            k: min(max(v, w_min), w_max)
            for k, v in weights.items()
        }
        
        return clamped
    
    def get_weight_history(self) -> List[Dict]:
        """Get history of weight updates for analysis"""
        return [r.to_dict() for r in self.update_history]
    
    def compute_weight_correlation_with_pnl(self) -> Dict[str, float]:
        """
        Compute correlation between weight changes and PnL.
        
        Useful for validating that learning is effective.
        """
        if len(self.update_history) < 5:
            return {}
        
        correlations = {}
        
        for component in self.COMPONENTS:
            weight_changes = []
            pnls = []
            
            for result in self.update_history:
                if result.updated:
                    old_w = result.old_weights.get(component, 0)
                    new_w = result.new_weights.get(component, 0)
                    weight_changes.append(new_w - old_w)
                    pnls.append(result.pnl)
            
            if len(weight_changes) >= 3:
                # Simple correlation
                if np.std(weight_changes) > 0 and np.std(pnls) > 0:
                    corr = np.corrcoef(weight_changes, pnls)[0, 1]
                    correlations[component] = corr
                else:
                    correlations[component] = 0.0
        
        return correlations
