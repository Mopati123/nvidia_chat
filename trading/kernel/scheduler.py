"""
scheduler.py — EG-weight-adapting scheduler (sole collapse authority)

The scheduler is the SOLE authority for collapse authorization.
No entity — including the architect — can force collapse.
Implements exponential gradient updates for operator weight adaptation.
"""

import numpy as np
import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum


class CollapseDecision(Enum):
    """Canonical collapse outcomes"""
    AUTHORIZED = "authorized"
    REFUSED = "refused"
    DEFERRED = "deferred"


@dataclass
class ExecutionToken:
    """
    ExecutionToken: cryptographic authorization primitive
    Issued only when all constraints pass through the full algebra.
    """
    token_id: str
    timestamp: float
    operator_weights: Dict[str, float]
    trajectory_hash: str
    authorization_signature: str
    lambda_parameters: Dict[str, float]
    
    def verify(self) -> bool:
        """Verify token integrity"""
        data = f"{self.token_id}:{self.timestamp}:{self.trajectory_hash}"
        expected = hashlib.sha256(data.encode()).hexdigest()[:32]
        return self.authorization_signature.startswith(expected)


@dataclass
class SchedulerState:
    """Internal scheduler state on probability simplex"""
    operator_weights: Dict[str, float] = field(default_factory=dict)
    learning_rate: float = 0.01
    entropy_reg: float = 0.1
    eg_iterations: int = 100
    convergence_threshold: float = 1e-6


class Scheduler:
    """
    EG-weight-adapting scheduler on probability simplex.
    Sole collapse authority. Scheduler sovereignty enforced.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.state = SchedulerState()
        self.collapse_history: List[ExecutionToken] = []
        self._initialize_weights()
        
    def _initialize_weights(self):
        """Initialize uniform weights over 18 operators"""
        operators = [
            "kinetic", "liquidity_pool", "order_block", "fvg", "macro_time",
            "price_delivery", "regime", "session", "risk", "sailing_lane",
            "sweep", "displacement", "breaker_block", "mitigation", "ote",
            "judas_swing", "accumulation", "projection"
        ]
        n = len(operators)
        self.state.operator_weights = {op: 1.0/n for op in operators}
        
    def compute_energy_gradient(self, 
                                trajectories: List[Dict],
                                market_state: Dict) -> Dict[str, float]:
        """
        Compute exponential gradient update for operator weights.
        Based on trajectory energy scores and market regime.
        """
        gradients = {}
        
        for op_name, weight in self.state.operator_weights.items():
            # Compute gradient based on trajectory alignment
            gradient = 0.0
            for traj in trajectories:
                op_score = traj.get(f"{op_name}_score", 0.0)
                gradient += op_score * traj.get("energy", 0.0)
            
            # Entropy regularization (exploration bonus)
            entropy_grad = -self.state.entropy_reg * np.log(weight + 1e-10)
            gradients[op_name] = gradient + entropy_grad
            
        return gradients
    
    def update_weights_eg(self, 
                         trajectories: List[Dict],
                         market_state: Dict) -> Dict[str, float]:
        """
        Exponential gradient weight update on probability simplex.
        Maintains Σw_i = 1, w_i > 0.
        """
        gradients = self.compute_energy_gradient(trajectories, market_state)
        
        # EG update: w_i ∝ w_i * exp(η * gradient_i)
        new_weights = {}
        for op_name, weight in self.state.operator_weights.items():
            grad = gradients.get(op_name, 0.0)
            new_weights[op_name] = weight * np.exp(self.state.learning_rate * grad)
        
        # Project back to simplex (normalize)
        total = sum(new_weights.values())
        self.state.operator_weights = {k: v/total for k, v in new_weights.items()}
        
        return self.state.operator_weights.copy()
    
    def authorize_collapse(self,
                          proposal: Dict,
                          projected_trajectories: List[Dict],
                          delta_s: float,
                          constraints_passed: bool,
                          reconciliation_clear: bool) -> Tuple[CollapseDecision, Optional[ExecutionToken]]:
        """
        SOLE COLLAPSE AUTHORITY.
        Evaluates full constraint algebra and issues ExecutionToken if authorized.
        
        Refusal-first: default is non-execution.
        """
        # Refusal-first: must explicitly pass all gates
        if not constraints_passed:
            return CollapseDecision.REFUSED, None
            
        if not reconciliation_clear:
            return CollapseDecision.REFUSED, None
            
        if delta_s > 0:  # Positive entropy = destruction of structure
            return CollapseDecision.REFUSED, None
            
        if not projected_trajectories:
            return CollapseDecision.REFUSED, None
        
        # Select best trajectory via weighted energy
        best_traj = self._select_trajectory(projected_trajectories)
        
        # Issue ExecutionToken
        token = self._issue_token(best_traj)
        self.collapse_history.append(token)
        
        return CollapseDecision.AUTHORIZED, token
    
    def _select_trajectory(self, trajectories: List[Dict]) -> Dict:
        """Select trajectory via operator-weighted scoring"""
        best_score = -float('inf')
        best_traj = None
        
        for traj in trajectories:
            score = 0.0
            for op_name, weight in self.state.operator_weights.items():
                op_contrib = traj.get(f"{op_name}_score", 0.0)
                score += weight * op_contrib
            
            # Add action functional contribution
            score += traj.get("action_score", 0.0)
            
            if score > best_score:
                best_score = score
                best_traj = traj
                
        return best_traj or trajectories[0]
    
    def _issue_token(self, trajectory: Dict) -> ExecutionToken:
        """Cryptographic authorization token issuance"""
        timestamp = time.time()
        token_id = hashlib.sha256(f"{timestamp}:{trajectory.get('id','')}".encode()).hexdigest()[:16]
        traj_hash = hashlib.sha256(str(trajectory).encode()).hexdigest()[:32]
        
        # Signature combines all authorization factors
        sig_data = f"{token_id}:{timestamp}:{traj_hash}"
        signature = hashlib.sha256(sig_data.encode()).hexdigest()
        
        # Lambda parameters for this collapse
        lambda_params = {
            "session_gate": 1.0,
            "risk_gate": 1.0,
            "regime_gate": 1.0,
            "reconciliation_gate": 1.0
        }
        
        return ExecutionToken(
            token_id=token_id,
            timestamp=timestamp,
            operator_weights=self.state.operator_weights.copy(),
            trajectory_hash=traj_hash,
            authorization_signature=signature,
            lambda_parameters=lambda_params
        )
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Current scheduler state for evidence emission"""
        return {
            "operator_weights": self.state.operator_weights,
            "learning_rate": self.state.learning_rate,
            "collapse_count": len(self.collapse_history),
            "sovereignty": "SCHEDULER_SOLE_AUTHORITY",
            "refusal_first": True
        }
