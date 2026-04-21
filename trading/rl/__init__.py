"""
RL Module for Trading

Provides reinforcement learning components for trajectory optimization.

Key Components:
- TradingEnvironment: Gym-style environment for RL
- ActorCritic: Policy and value network
- PPOSchedulerAgent: PPO training and inference
- train: Training pipeline
"""

from .environment import TradingEnvironment, SyntheticTradingEnv, TradeResult
from .policy import ActorCritic, RolloutBuffer
from .scheduler_agent import PPOSchedulerAgent, get_agent, reset_agent

__all__ = [
    'TradingEnvironment',
    'SyntheticTradingEnv',
    'TradeResult',
    'ActorCritic',
    'RolloutBuffer',
    'PPOSchedulerAgent',
    'get_agent',
    'reset_agent',
]
