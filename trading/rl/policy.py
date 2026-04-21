"""
Actor-Critic Policy Network

Shared feature extractor with separate actor and critic heads.
Actor outputs action distribution, critic outputs value estimate.

Architecture:
- Shared: 166 (state) → 256 → 128
- Actor: 128 → n_actions (softmax)
- Critic: 128 → 1
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple
import numpy as np


class ActorCritic(nn.Module):
    """
    Actor-Critic network for PPO.
    
    Args:
        state_dim: Dimension of state vector (166)
        action_dim: Number of discrete actions (n_trajectories)
        hidden_dim: Hidden layer size (default 256)
    
    Returns:
        action_logits: Logits for action distribution
        value: State value estimate
    """
    
    def __init__(self,
                 state_dim: int = 166,
                 action_dim: int = 5,
                 hidden_dim: int = 256):
        super().__init__()
        
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # Shared feature extractor
        self.feature_net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1),
            
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim // 2),
            nn.Dropout(0.1)
        )
        
        # Actor head (policy)
        self.actor = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, action_dim)
        )
        
        # Critic head (value function)
        self.critic = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1)
        )
        
        # Initialize weights
        self._init_weights()
    
    def _init_weights(self):
        """Orthogonal initialization for better training stability"""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
    
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through both actor and critic.
        
        Args:
            state: State tensor (batch, state_dim) or (state_dim,)
        
        Returns:
            action_logits: (batch, action_dim) or (action_dim,)
            value: (batch, 1) or (1,)
        """
        # Ensure state is 2D
        if state.dim() == 1:
            state = state.unsqueeze(0)
            squeeze = True
        else:
            squeeze = False
        
        # Shared features
        features = self.feature_net(state)
        
        # Actor output (logits)
        action_logits = self.actor(features)
        
        # Critic output (value)
        value = self.critic(features)
        
        if squeeze:
            action_logits = action_logits.squeeze(0)
            value = value.squeeze(0)
        
        return action_logits, value
    
    def get_action(self, state: torch.Tensor, deterministic: bool = False) -> Tuple[int, float, float]:
        """
        Sample action from policy.
        
        Args:
            state: State tensor
            deterministic: If True, return argmax; else sample
        
        Returns:
            action: Selected action index
            log_prob: Log probability of action
            value: Estimated value of state
        """
        with torch.no_grad():
            action_logits, value = self.forward(state)
            
            # Action distribution
            probs = F.softmax(action_logits, dim=-1)
            
            if deterministic:
                action = torch.argmax(probs, dim=-1)
            else:
                action = torch.multinomial(probs, 1).squeeze()
            
            # Log probability
            log_prob = F.log_softmax(action_logits, dim=-1)[action]
            
            return action.item(), log_prob.item(), value.item()
    
    def get_value(self, state: torch.Tensor) -> float:
        """Get value estimate for state"""
        with torch.no_grad():
            _, value = self.forward(state)
            return value.item()
    
    def evaluate_actions(self,
                        state: torch.Tensor,
                        action: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Evaluate actions for PPO update.
        
        Args:
            state: Batch of states (batch, state_dim)
            action: Batch of actions (batch,)
        
        Returns:
            log_probs: Log probs of actions (batch,)
            values: Value estimates (batch,)
            entropy: Policy entropy (batch,)
        """
        action_logits, values = self.forward(state)
        
        # Action log probabilities
        log_probs = F.log_softmax(action_logits, dim=-1)
        log_probs = log_probs.gather(1, action.unsqueeze(1)).squeeze(1)
        
        # Policy entropy (for exploration bonus)
        probs = F.softmax(action_logits, dim=-1)
        entropy = -(probs * log_probs).sum(dim=-1)
        
        return log_probs, values.squeeze(1), entropy


class RolloutBuffer:
    """
    Buffer for storing PPO rollouts.
    
    Stores trajectories for on-policy PPO updates.
    Cleared after each update.
    """
    
    def __init__(self, buffer_size: int = 2048, state_dim: int = 166):
        self.buffer_size = buffer_size
        self.state_dim = state_dim
        
        self.states = np.zeros((buffer_size, state_dim), dtype=np.float32)
        self.actions = np.zeros(buffer_size, dtype=np.int64)
        self.rewards = np.zeros(buffer_size, dtype=np.float32)
        self.log_probs = np.zeros(buffer_size, dtype=np.float32)
        self.values = np.zeros(buffer_size, dtype=np.float32)
        self.dones = np.zeros(buffer_size, dtype=np.float32)
        
        self.pos = 0
        self.full = False
    
    def add(self,
           state: np.ndarray,
           action: int,
           reward: float,
           log_prob: float,
           value: float,
           done: bool):
        """Add single transition to buffer"""
        if self.full:
            return
        
        idx = self.pos
        self.states[idx] = state
        self.actions[idx] = action
        self.rewards[idx] = reward
        self.log_probs[idx] = log_prob
        self.values[idx] = value
        self.dones[idx] = float(done)
        
        self.pos += 1
        if self.pos >= self.buffer_size:
            self.full = True
    
    def get(self) -> Tuple[torch.Tensor, ...]:
        """Get all data from buffer as tensors"""
        if not self.full and self.pos == 0:
            return None
        
        end_idx = self.buffer_size if self.full else self.pos
        
        return (
            torch.FloatTensor(self.states[:end_idx]),
            torch.LongTensor(self.actions[:end_idx]),
            torch.FloatTensor(self.rewards[:end_idx]),
            torch.FloatTensor(self.log_probs[:end_idx]),
            torch.FloatTensor(self.values[:end_idx]),
            torch.FloatTensor(self.dones[:end_idx])
        )
    
    def clear(self):
        """Clear buffer"""
        self.pos = 0
        self.full = False
    
    def __len__(self):
        return self.buffer_size if self.full else self.pos
