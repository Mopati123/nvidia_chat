"""
PPO Agent for Trajectory Selection

Implements Proximal Policy Optimization for learning optimal
trajectory selection policy.

Key Features:
- GAE for advantage estimation
- Clipped surrogate objective
- Value function clipping
- Entropy bonus for exploration
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

from .policy import ActorCritic, RolloutBuffer

logger = logging.getLogger(__name__)


class PPOSchedulerAgent:
    """
    PPO agent for trajectory selection in scheduler.
    
    Hyperparameters:
    - lr: 3e-4 (learning rate)
    - gamma: 0.99 (discount factor)
    - gae_lambda: 0.95 (GAE lambda)
    - clip_epsilon: 0.2 (PPO clipping)
    - entropy_coef: 0.01 (entropy bonus)
    - value_coef: 0.5 (value loss weight)
    - max_grad_norm: 0.5 (gradient clipping)
    - update_epochs: 4 (PPO epochs per batch)
    """
    
    def __init__(self,
                 state_dim: int = 166,
                 action_dim: int = 5,
                 lr: float = 3e-4,
                 gamma: float = 0.99,
                 gae_lambda: float = 0.95,
                 clip_epsilon: float = 0.2,
                 entropy_coef: float = 0.01,
                 value_coef: float = 0.5,
                 max_grad_norm: float = 0.5,
                 update_epochs: int = 4,
                 batch_size: int = 64,
                 buffer_size: int = 2048,
                 device: str = "auto"):
        
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.max_grad_norm = max_grad_norm
        self.update_epochs = update_epochs
        self.batch_size = batch_size
        
        # Device
        self.device = self._get_device(device)
        
        # Network
        self.network = ActorCritic(state_dim, action_dim).to(self.device)
        self.optimizer = optim.Adam(self.network.parameters(), lr=lr)
        
        # Buffer
        self.buffer = RolloutBuffer(buffer_size, state_dim)
        
        # Tracking
        self.n_updates = 0
        self.total_steps = 0
        self.recent_pnl: List[float] = []  # T2-C: rolling PnL history for state vector
        
        logger.info(f"PPO Agent initialized on {self.device}")
    
    def _get_device(self, device: str) -> torch.device:
        """Auto-detect device"""
        if device == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            elif torch.backends.mps.is_available():
                return torch.device("mps")
            else:
                return torch.device("cpu")
        return torch.device(device)
    
    def select_action(self,
                     state: np.ndarray,
                     deterministic: bool = False) -> Tuple[int, float, float]:
        """
        Select action given state.
        
        Args:
            state: State vector (state_dim,)
            deterministic: If True, return argmax
        
        Returns:
            action: Selected action index
            log_prob: Log probability
            value: State value estimate
        """
        state_tensor = torch.FloatTensor(state).to(self.device)
        action, log_prob, value = self.network.get_action(state_tensor, deterministic)
        return action, log_prob, value
    
    def store_transition(self,
                        state: np.ndarray,
                        action: int,
                        reward: float,
                        log_prob: float,
                        value: float,
                        done: bool):
        """Store transition in buffer"""
        self.buffer.add(state, action, reward, log_prob, value, done)
        self.total_steps += 1
        # T2-C: maintain rolling PnL history used by PPOPaperHook state builder
        self.recent_pnl.append(float(reward))
        if len(self.recent_pnl) > 100:
            self.recent_pnl = self.recent_pnl[-100:]
    
    def update(self) -> Dict[str, float]:
        """
        Perform PPO update on collected rollouts.
        
        Returns:
            Dict with update metrics
        """
        if len(self.buffer) < self.batch_size:
            return {}
        
        # Get data from buffer
        states, actions, rewards, old_log_probs, values, dones = self.buffer.get()
        
        # Move to device
        states = states.to(self.device)
        actions = actions.to(self.device)
        rewards = rewards.to(self.device)
        old_log_probs = old_log_probs.to(self.device)
        values = values.to(self.device)
        dones = dones.to(self.device)
        
        # Compute advantages using GAE
        advantages = self._compute_gae(rewards, values, dones)
        
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # Compute returns (target values)
        returns = advantages + values
        
        # PPO update epochs
        total_loss = 0
        policy_loss = 0
        value_loss = 0
        entropy_bonus = 0
        
        n_samples = len(states)
        
        for epoch in range(self.update_epochs):
            # Mini-batch updates
            indices = torch.randperm(n_samples)
            
            for start in range(0, n_samples, self.batch_size):
                end = min(start + self.batch_size, n_samples)
                batch_idx = indices[start:end]
                
                batch_states = states[batch_idx]
                batch_actions = actions[batch_idx]
                batch_old_log_probs = old_log_probs[batch_idx]
                batch_advantages = advantages[batch_idx]
                batch_returns = returns[batch_idx]
                
                # Evaluate actions
                log_probs, state_values, entropy = self.network.evaluate_actions(
                    batch_states, batch_actions
                )
                
                # Policy loss (clipped surrogate)
                ratio = torch.exp(log_probs - batch_old_log_probs)
                surr1 = ratio * batch_advantages
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * batch_advantages
                policy_loss_batch = -torch.min(surr1, surr2).mean()
                
                # Value loss
                value_loss_batch = F.mse_loss(state_values, batch_returns)
                
                # Entropy bonus (encourage exploration)
                entropy_loss_batch = -entropy.mean()
                
                # Total loss
                loss = (
                    policy_loss_batch +
                    self.value_coef * value_loss_batch +
                    self.entropy_coef * entropy_loss_batch
                )
                
                # Optimization step
                self.optimizer.zero_grad()
                loss.backward()
                
                # Gradient clipping
                nn.utils.clip_grad_norm_(self.network.parameters(), self.max_grad_norm)
                
                self.optimizer.step()
                
                # Track losses
                total_loss += loss.item()
                policy_loss += policy_loss_batch.item()
                value_loss += value_loss_batch.item()
                entropy_bonus += entropy_loss_batch.item()
        
        # Clear buffer after update
        self.buffer.clear()
        
        self.n_updates += 1
        
        n_batches = self.update_epochs * (n_samples // self.batch_size + 1)
        
        return {
            'total_loss': total_loss / n_batches,
            'policy_loss': policy_loss / n_batches,
            'value_loss': value_loss / n_batches,
            'entropy': entropy_bonus / n_batches,
            'update': self.n_updates
        }
    
    def _compute_gae(self,
                    rewards: torch.Tensor,
                    values: torch.Tensor,
                    dones: torch.Tensor) -> torch.Tensor:
        """
        Compute Generalized Advantage Estimation (GAE).
        
        GAE advantages reduce variance while maintaining low bias.
        
        Args:
            rewards: Reward tensor
            values: Value estimates
            dones: Done flags
        
        Returns:
            Advantage tensor
        """
        n = len(rewards)
        advantages = torch.zeros_like(rewards)
        last_gae = 0
        
        for t in reversed(range(n)):
            if t == n - 1:
                next_value = 0
            else:
                next_value = values[t + 1]
            
            # TD error
            delta = rewards[t] + self.gamma * next_value * (1 - dones[t]) - values[t]
            
            # GAE
            last_gae = delta + self.gamma * self.gae_lambda * (1 - dones[t]) * last_gae
            advantages[t] = last_gae
        
        return advantages
    
    def save(self, path: str):
        """Save agent state"""
        torch.save({
            'network_state_dict': self.network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'n_updates': self.n_updates,
            'total_steps': self.total_steps
        }, path)
        logger.info(f"Agent saved to {path}")
    
    def load(self, path: str):
        """Load agent state"""
        checkpoint = torch.load(path, map_location=self.device)
        self.network.load_state_dict(checkpoint['network_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.n_updates = checkpoint.get('n_updates', 0)
        self.total_steps = checkpoint.get('total_steps', 0)
        logger.info(f"Agent loaded from {path}")


# Global singleton
_agent: Optional[PPOSchedulerAgent] = None


def get_agent(**kwargs) -> PPOSchedulerAgent:
    """Get or create global agent"""
    global _agent
    if _agent is None:
        _agent = PPOSchedulerAgent(**kwargs)
    return _agent


def reset_agent():
    """Reset global agent (for testing)"""
    global _agent
    _agent = None
