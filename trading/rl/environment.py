"""
Trading Environment for RL Training

Gym-style environment for PPO agent training.
Handles state representation, reward computation, and episode management.

First Principles:
- State captures market context + available trajectories
- Reward based on realized PnL (not predictions)
- Episodes end on trade completion or timeout
"""

import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Result of a completed trade"""
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    duration_steps: int
    max_drawdown: float
    win: bool
    timestamp: str


class TradingEnvironment:
    """
    Trading environment for RL agent.
    
    State Space (166-dim):
    - Market embedding: 128 dims (from Phase 1)
    - Trajectory energies: 5 dims (one per trajectory)
    - Trajectory actions: 5 dims (action values)
    - Operator scores: 18 dims (ICT operator activations)
    - Recent PnL history: 10 dims (last 10 trades)
    
    Action Space:
    - Discrete: Select trajectory (0 to n_trajectories-1)
    
    Reward:
    - Primary: Realized PnL (scaled)
    - Penalty: Risk-adjusted drawdown
    - Bonus: Consistency reward
    """
    
    def __init__(self,
                 n_trajectories: int = 5,
                 max_steps_per_episode: int = 20,
                 transaction_cost: float = 0.001):
        self.n_trajectories = n_trajectories
        self.max_steps = max_steps_per_episode
        self.transaction_cost = transaction_cost
        
        # State dimensions
        self.embedding_dim = 128
        self.operator_dim = 18
        self.history_len = 10
        
        self.state_dim = (
            self.embedding_dim +      # Market embedding
            self.n_trajectories +     # Trajectory energies
            self.n_trajectories +     # Trajectory actions
            self.operator_dim +       # Operator scores
            self.history_len          # Recent PnL history
        )
        
        # Episode tracking
        self.current_step = 0
        self.episode_history = []
        self.recent_pnls = []
        
        # Current state cache
        self.current_state = None
        self.available_trajectories = None
        
        logger.info(f"TradingEnvironment initialized: state_dim={self.state_dim}")
    
    def reset(self,
             market_embedding: np.ndarray,
             trajectories: List[Dict],
             operator_scores: Dict[str, float]) -> np.ndarray:
        """
        Reset environment for new episode.
        
        Args:
            market_embedding: 128-dim market state embedding
            trajectories: List of trajectory dicts with 'energy', 'action', 'id'
            operator_scores: Dict of operator scores
        
        Returns:
            Initial state vector (166-dim)
        """
        self.current_step = 0
        self.episode_history = []
        self.available_trajectories = trajectories
        
        # Build initial state
        self.current_state = self._build_state(
            market_embedding=market_embedding,
            trajectories=trajectories,
            operator_scores=operator_scores,
            recent_pnls=self.recent_pnls
        )
        
        return self.current_state
    
    def step(self,
            action: int,
            trade_result: Optional[TradeResult] = None) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Execute action and return next state, reward, done, info.
        
        Args:
            action: Trajectory index to select
            trade_result: Result if trade completed (None if still open)
        
        Returns:
            next_state: New state vector
            reward: Scalar reward
            done: Whether episode ended
            info: Additional info dict
        """
        self.current_step += 1
        
        # Compute reward if trade completed
        if trade_result:
            reward = self._compute_reward(trade_result)
            done = True
            
            # Update recent PnLs
            self.recent_pnls.append(trade_result.pnl_pct)
            if len(self.recent_pnls) > self.history_len:
                self.recent_pnls = self.recent_pnls[-self.history_len:]
        else:
            # Small step penalty to encourage faster decisions
            reward = -0.001
            done = self.current_step >= self.max_steps
        
        # Build next state (will be updated externally with new market data)
        info = {
            'action': action,
            'step': self.current_step,
            'trajectory_id': self._get_trajectory_id(action),
            'trade_completed': trade_result is not None
        }
        
        return self.current_state, reward, done, info
    
    def _build_state(self,
                    market_embedding: np.ndarray,
                    trajectories: List[Dict],
                    operator_scores: Dict[str, float],
                    recent_pnls: List[float]) -> np.ndarray:
        """
        Build 166-dim state vector from components.
        
        Args:
            market_embedding: 128-dim embedding
            trajectories: List of trajectory dicts
            operator_scores: Operator score dict
            recent_pnls: List of recent PnL values
        
        Returns:
            Concatenated state vector
        """
        # Pad or truncate embedding
        if len(market_embedding) < self.embedding_dim:
            embedding = np.pad(market_embedding, 
                             (0, self.embedding_dim - len(market_embedding)))
        else:
            embedding = market_embedding[:self.embedding_dim]
        
        # Extract trajectory features
        energies = []
        actions = []
        for traj in trajectories[:self.n_trajectories]:
            energies.append(traj.get('energy', 0.0))
            actions.append(traj.get('action', 0.0))
        
        # Pad if fewer trajectories
        while len(energies) < self.n_trajectories:
            energies.append(0.0)
            actions.append(0.0)
        
        # Extract operator scores (18 operators)
        default_ops = {
            'kinetic': 0.5, 'potential': 0.5, 'liquidity': 0.5, 'ob': 0.5,
            'fvg': 0.5, 'breaker': 0.5, 'orderblock': 0.5, 'mitigation': 0.5,
            'sweep': 0.5, 'choch': 0.5, 'bos': 0.5, 'fib': 0.5,
            'pdi': 0.5, 'ndi': 0.5, 'adx': 0.5, 'atr': 0.5,
            'rsi': 0.5, 'momentum': 0.5
        }
        default_ops.update(operator_scores)
        op_scores = [default_ops.get(k, 0.5) for k in sorted(default_ops.keys())]
        op_scores = op_scores[:self.operator_dim]
        
        # Pad recent PnLs
        pnls = list(recent_pnls) if recent_pnls else []
        while len(pnls) < self.history_len:
            pnls.insert(0, 0.0)  # Pad with zeros at start
        pnls = pnls[:self.history_len]
        
        # Concatenate all features
        state = np.concatenate([
            embedding,
            np.array(energies),
            np.array(actions),
            np.array(op_scores),
            np.array(pnls)
        ])
        
        # Normalize
        state = self._normalize_state(state)
        
        return state.astype(np.float32)
    
    def _normalize_state(self, state: np.ndarray) -> np.ndarray:
        """Normalize state to reasonable range"""
        # Clip extreme values
        state = np.clip(state, -10, 10)
        
        # Scale embedding separately
        state[:self.embedding_dim] = state[:self.embedding_dim] / np.linalg.norm(
            state[:self.embedding_dim] + 1e-8
        )
        
        return state
    
    def _compute_reward(self, trade_result: TradeResult) -> float:
        """
        Compute reward from trade result.
        
        Components:
        1. PnL reward (primary)
        2. Risk penalty (drawdown)
        3. Consistency bonus
        
        Args:
            trade_result: TradeResult object
        
        Returns:
            Scalar reward
        """
        # Base reward from PnL (scale to reasonable range)
        pnl_reward = trade_result.pnl_pct * 100  # Scale up
        
        # Transaction cost penalty
        cost_penalty = self.transaction_cost * 100
        
        # Drawdown penalty (risk-adjusted)
        drawdown_penalty = trade_result.max_drawdown * 50
        
        # Consistency bonus (if win rate > 50%)
        win_bonus = 0.05 if trade_result.win else -0.05
        
        # Duration penalty (encourage faster profitable trades)
        duration_penalty = -0.001 * trade_result.duration_steps
        
        total_reward = (
            pnl_reward -
            cost_penalty -
            drawdown_penalty +
            win_bonus +
            duration_penalty
        )
        
        return float(total_reward)
    
    def _get_trajectory_id(self, action: int) -> Optional[str]:
        """Get trajectory ID from action index"""
        if self.available_trajectories and 0 <= action < len(self.available_trajectories):
            return self.available_trajectories[action].get('id')
        return None
    
    def update_market_state(self,
                          market_embedding: np.ndarray,
                          trajectories: List[Dict],
                          operator_scores: Dict[str, float]):
        """
        Update state with new market data (called between steps).
        
        Args:
            market_embedding: New market embedding
            trajectories: New trajectory set
            operator_scores: Updated operator scores
        """
        self.available_trajectories = trajectories
        self.current_state = self._build_state(
            market_embedding=market_embedding,
            trajectories=trajectories,
            operator_scores=operator_scores,
            recent_pnls=self.recent_pnls
        )


class SyntheticTradingEnv(TradingEnvironment):
    """
    Synthetic environment for initial RL training.
    
    Generates synthetic trade outcomes for training before
    moving to real market data.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rng = np.random.RandomState(42)
        
    def simulate_trade_result(self,
                            trajectory: Dict,
                            market_state: Dict) -> TradeResult:
        """
        Simulate trade outcome for synthetic training.
        
        Args:
            trajectory: Selected trajectory
            market_state: Current market state
        
        Returns:
            Synthetic TradeResult
        """
        # Base win probability from trajectory quality
        base_prob = 0.5
        if trajectory.get('energy', 0) < 0.5:
            base_prob += 0.1  # Lower energy = better trajectory
        
        # Add noise
        win = self.rng.random() < base_prob
        
        # Generate PnL
        if win:
            pnl_pct = self.rng.exponential(0.02)  # Mean 2% win
        else:
            pnl_pct = -self.rng.exponential(0.015)  # Mean 1.5% loss
        
        # Generate other metrics
        entry_price = market_state.get('current_price', 1.0)
        exit_price = entry_price * (1 + pnl_pct)
        max_dd = abs(pnl_pct) * self.rng.uniform(0.3, 0.8) if not win else pnl_pct * 0.3
        
        return TradeResult(
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl_pct * entry_price,
            pnl_pct=pnl_pct,
            duration_steps=self.rng.randint(5, 20),
            max_drawdown=max_dd,
            win=win,
            timestamp=datetime.now().isoformat()
        )
