"""
scheduler.py — EG-weight-adapting scheduler (sole collapse authority)

The scheduler is the SOLE authority for collapse authorization.
No entity — including the architect — can force collapse.
Implements exponential gradient updates for operator weight adaptation.
"""

import numpy as np
import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

logger = logging.getLogger(__name__)


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

    def is_valid(self) -> bool:
        """Compatibility alias used by the Apex execution gate."""
        return self.verify()


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
        
        # RL integration (optional)
        self.use_rl = config.get('use_rl', False) if config else False
        self.rl_threshold = config.get('rl_threshold', 0.7) if config else 0.7
        self.rl_agent = None
        self._last_rl_state = None
        self._last_rl_action = None
        
        if self.use_rl:
            try:
                from ..rl import get_agent
                self.rl_agent = get_agent()
            except Exception as e:
                logger.warning(f"Could not load RL agent: {e}, using entropy-only")
        
        # Action component weights for backward learning (L/T/E/R)
        self.action_weights = {
            'L': 0.50,  # Liquidity
            'T': 0.30,  # Time
            'E': 0.10,  # Entry
            'R': 0.10,  # Risk
        }
        
        # Weight update operator (lazy import)
        self._weight_update_operator = None
        
    def get_weight_update_operator(self):
        """Lazy initialization of weight update operator"""
        if self._weight_update_operator is None:
            from ..core.learning import WeightUpdateOperator
            self._weight_update_operator = WeightUpdateOperator()
        return self._weight_update_operator
    
    def update_action_weights(self, 
                             pnl: float,
                             delta_s: float,
                             status: str,
                             contrib: Dict[str, float],
                             constraints_passed: bool = True,
                             evidence_complete: bool = True) -> Dict:
        """
        Update action weights via backward learning law.
        
        Called post-reconciliation to adapt the action landscape
        based on real-world outcomes.
        
        Args:
            pnl: Realized profit/loss
            delta_s: Entropy reduction
            status: Reconciliation status ('match', 'mismatch', 'rollback')
            contrib: Path contributions {'L': val, 'T': val, 'E': val, 'R': val}
            constraints_passed: Whether constraints were satisfied
            evidence_complete: Whether evidence is complete
        
        Returns:
            Weight update result dict
        """
        operator = self.get_weight_update_operator()
        
        result = operator.update(
            weights=self.action_weights,
            contrib=contrib,
            pnl=pnl,
            delta_s=delta_s,
            status=status,
            constraints_passed=constraints_passed,
            collapse_authorized=True,  # Only called if authorized
            evidence_complete=evidence_complete
        )
        
        if result.updated:
            self.action_weights = result.new_weights
            logger.info(f"Action weights updated: L={result.new_weights['L']:.3f}, "
                       f"T={result.new_weights['T']:.3f}, "
                       f"E={result.new_weights['E']:.3f}, "
                       f"R={result.new_weights['R']:.3f}")
        
        return result.to_dict()
    
    def get_action_weights(self) -> Dict[str, float]:
        """Get current action component weights"""
        return self.action_weights.copy()
        
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
                # Operator scores stored with bare names (kinetic, fvg, etc.)
                # not with _score suffix
                op_score = traj.get(op_name, traj.get(f"{op_name}_score", 0.0))
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
            
        # Entropy gate: refuse if entropy exceeds calibrated threshold
        # Variance-based delta_s is always >= 0, so we check against threshold
        # not just positive. Lower variance = more structure = acceptable.
        entropy_threshold = self.config.get('max_entropy', 0.5)  # Calibrated threshold
        if delta_s > entropy_threshold:
            return CollapseDecision.REFUSED, None
            
        if not projected_trajectories:
            return CollapseDecision.REFUSED, None
        
        # Select best trajectory via weighted energy (with RL if enabled)
        best_traj = self._select_trajectory(projected_trajectories, proposal)
        
        # Issue ExecutionToken
        token = self._issue_token(best_traj)
        self.collapse_history.append(token)
        
        return CollapseDecision.AUTHORIZED, token
    
    def _select_trajectory(self, trajectories: List[Dict], market_state: Dict = None) -> Dict:
        """
        Select trajectory via operator-weighted scoring with optional RL augmentation.
        
        Args:
            trajectories: List of candidate trajectories
            market_state: Optional market state for RL feature extraction
        
        Returns:
            Selected trajectory dict
        """
        # RL-augmented selection
        if self.use_rl and self.rl_agent and market_state is not None:
            try:
                # Build RL state
                rl_state = self._build_rl_state(market_state, trajectories)
                
                # Get RL recommendation
                action, log_prob, value = self.rl_agent.select_action(rl_state)
                
                # Store for potential training
                self._last_rl_state = rl_state
                self._last_rl_action = action
                
                # Use RL if confidence high enough (value estimate)
                confidence = self._compute_rl_confidence(value)
                
                if confidence > self.rl_threshold:
                    # RL override - use RL selected trajectory
                    if 0 <= action < len(trajectories):
                        logger.debug(f"RL selection: trajectory {action} (confidence={confidence:.2f})")
                        return trajectories[action]
            except Exception as e:
                logger.debug(f"RL selection failed: {e}, falling back to entropy")
        
        # Fallback: Entropy-based (operator-weighted) selection
        best_score = -float('inf')
        best_traj = None
        
        for i, traj in enumerate(trajectories):
            # Weighted sum of operator scores
            score = sum(
                self.state.operator_weights.get(op, 0) * value
                for op, value in traj.get("operator_scores", {}).items()
            )
            
            # Penalize high action (path integral penalization)
            score -= 0.1 * traj.get("action", 0)
            
            # Hybrid: blend with RL value if available
            if hasattr(self, '_last_rl_action') and self._last_rl_action == i:
                # Slight boost to RL-recommended trajectory even if not selected
                score += 0.05
            
            if score > best_score:
                best_score = score
                best_traj = traj
                
        return best_traj if best_traj else trajectories[0]
    
    def _build_rl_state(self, market_state: Dict, trajectories: List[Dict]) -> np.ndarray:
        """
        Build RL state vector from market state and trajectories.
        
        Args:
            market_state: Dict with market data
            trajectories: List of trajectory dicts
        
        Returns:
            166-dim state vector
        """
        # Get market embedding from memory module
        try:
            from ...memory import get_embedder
            ohlcv = market_state.get('ohlc', [])
            if len(ohlcv) >= 100:
                embedder = get_embedder()
                embedding = embedder.encode(ohlcv)
            else:
                embedding = np.zeros(128)
        except:
            embedding = np.zeros(128)
        
        # Extract trajectory features
        energies = [t.get('energy', 0.0) for t in trajectories[:5]]
        actions = [t.get('action', 0.0) for t in trajectories[:5]]
        
        # Pad if needed
        while len(energies) < 5:
            energies.append(0.0)
            actions.append(0.0)
        
        # Operator scores
        op_scores = list(market_state.get('operator_scores', {}).values())
        while len(op_scores) < 18:
            op_scores.append(0.5)
        op_scores = op_scores[:18]
        
        # Recent PnL history (placeholder)
        recent_pnls = [0.0] * 10
        
        # Concatenate
        state = np.concatenate([
            embedding,
            np.array(energies),
            np.array(actions),
            np.array(op_scores),
            np.array(recent_pnls)
        ]).astype(np.float32)
        
        return state
    
    def _compute_rl_confidence(self, value: float) -> float:
        """
        Compute confidence score from RL value estimate.
        
        Args:
            value: RL value estimate
        
        Returns:
            Confidence score in [0, 1]
        """
        # Normalize value to confidence (sigmoid-like)
        # Higher value = higher confidence
        confidence = 1.0 / (1.0 + np.exp(-value))
        return float(confidence)
    
    def report_trade_outcome(self, pnl: float, done: bool = True):
        """
        Report trade outcome for RL training.
        
        Args:
            pnl: Realized PnL
            done: Whether episode is complete
        """
        if self.use_rl and self.rl_agent and self._last_rl_state is not None:
            try:
                # Compute reward from PnL
                reward = pnl * 100  # Scale up
                
                # Get value estimate
                value = self.rl_agent.network.get_value(
                    torch.FloatTensor(self._last_rl_state)
                )
                
                # Store transition
                self.rl_agent.store_transition(
                    self._last_rl_state,
                    self._last_rl_action,
                    reward,
                    0.0,  # log_prob not available post-hoc
                    value,
                    done
                )
                
                # Trigger update if buffer full
                if len(self.rl_agent.buffer) >= self.rl_agent.buffer.buffer_size:
                    metrics = self.rl_agent.update()
                    logger.debug(f"RL update: loss={metrics.get('total_loss', 0):.4f}")
                
            except Exception as e:
                logger.debug(f"RL outcome reporting failed: {e}")
            finally:
                # Clear stored state
                self._last_rl_state = None
                self._last_rl_action = None
    
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
