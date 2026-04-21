"""
RL Training Pipeline

Trains PPO agent on synthetic trading environment.

Stages:
1. Synthetic training (validate architecture)
2. Shadow trading (collect live experience)
3. Paper trading (validate performance)
"""

import torch
import numpy as np
from typing import Dict, List
from pathlib import Path
import logging
from tqdm import tqdm

from .environment import SyntheticTradingEnv
from .scheduler_agent import PPOSchedulerAgent

logger = logging.getLogger(__name__)


def train_synthetic(
    n_episodes: int = 1000,
    max_steps: int = 50,
    save_dir: str = "models/rl_agent",
    device: str = "cpu"
) -> Dict:
    """
    Train agent on synthetic trading environment.
    
    This is Stage 1 training - validates the RL architecture
    works before moving to real market data.
    
    Args:
        n_episodes: Number of training episodes
        max_steps: Max steps per episode
        save_dir: Directory to save models
        device: Device for training
    
    Returns:
        Training history dict
    """
    logger.info("="*70)
    logger.info("STAGE 1: RL Training on Synthetic Data")
    logger.info("="*70)
    
    # Create environment
    env = SyntheticTradingEnv(n_trajectories=5, max_steps_per_episode=max_steps)
    
    # Create agent
    agent = PPOSchedulerAgent(
        state_dim=env.state_dim,
        action_dim=env.n_trajectories,
        device=device
    )
    
    # Training metrics
    episode_rewards = []
    episode_lengths = []
    win_rates = []
    
    best_avg_reward = float('-inf')
    
    for episode in tqdm(range(n_episodes), desc="Training"):
        # Generate random market state
        market_embedding = np.random.randn(env.embedding_dim)
        
        # Generate random trajectories
        trajectories = [
            {
                'id': f'traj_{i}',
                'energy': np.random.randn(),
                'action': np.random.randn()
            }
            for i in range(env.n_trajectories)
        ]
        
        operator_scores = {
            k: np.random.randn() * 0.1 + 0.5
            for k in ['kinetic', 'potential', 'liquidity', 'ob', 'fvg']
        }
        
        # Reset environment
        state = env.reset(market_embedding, trajectories, operator_scores)
        
        episode_reward = 0
        episode_wins = 0
        step_count = 0
        
        for step in range(max_steps):
            # Select action
            action, log_prob, value = agent.select_action(state)
            
            # Simulate trade outcome
            selected_trajectory = trajectories[action]
            market_state = {'current_price': 1.0}
            trade_result = env.simulate_trade_result(selected_trajectory, market_state)
            
            # Step environment
            next_state, reward, done, info = env.step(action, trade_result)
            
            # Store transition
            agent.store_transition(state, action, reward, log_prob, value, done)
            
            episode_reward += reward
            step_count += 1
            
            if trade_result.win:
                episode_wins += 1
            
            state = next_state
            
            # Update agent when buffer is full
            if len(agent.buffer) >= agent.buffer.buffer_size:
                metrics = agent.update()
                if metrics:
                    logger.debug(f"Update: loss={metrics['total_loss']:.4f}")
            
            if done:
                break
        
        # Track metrics
        episode_rewards.append(episode_reward)
        episode_lengths.append(step_count)
        win_rates.append(episode_wins / max(step_count, 1))
        
        # Log progress every 100 episodes
        if (episode + 1) % 100 == 0:
            avg_reward = np.mean(episode_rewards[-100:])
            avg_length = np.mean(episode_lengths[-100:])
            avg_win_rate = np.mean(win_rates[-100:])
            
            logger.info(
                f"Episode {episode + 1}: "
                f"avg_reward={avg_reward:.4f}, "
                f"avg_length={avg_length:.1f}, "
                f"win_rate={avg_win_rate:.2%}"
            )
            
            # Save best model
            if avg_reward > best_avg_reward:
                best_avg_reward = avg_reward
                save_path = Path(save_dir)
                save_path.mkdir(parents=True, exist_ok=True)
                agent.save(save_path / "best_model.pt")
    
    # Final save
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    agent.save(save_path / "final_model.pt")
    
    logger.info("\n" + "="*70)
    logger.info("Stage 1 Complete!")
    logger.info(f"Best avg reward: {best_avg_reward:.4f}")
    logger.info(f"Final avg reward: {np.mean(episode_rewards[-100:]):.4f}")
    logger.info(f"Final win rate: {np.mean(win_rates[-100:]):.2%}")
    logger.info("="*70)
    
    return {
        'episode_rewards': episode_rewards,
        'episode_lengths': episode_lengths,
        'win_rates': win_rates,
        'best_reward': best_avg_reward
    }


def evaluate_agent(
    agent: PPOSchedulerAgent,
    env: SyntheticTradingEnv,
    n_episodes: int = 100,
    deterministic: bool = True
) -> Dict:
    """
    Evaluate trained agent.
    
    Args:
        agent: Trained PPO agent
        env: Trading environment
        n_episodes: Number of evaluation episodes
        deterministic: Use deterministic policy
    
    Returns:
        Evaluation metrics
    """
    episode_rewards = []
    episode_wins = []
    
    for _ in tqdm(range(n_episodes), desc="Evaluating"):
        # Generate random market state
        market_embedding = np.random.randn(env.embedding_dim)
        
        trajectories = [
            {
                'id': f'traj_{i}',
                'energy': np.random.randn(),
                'action': np.random.randn()
            }
            for i in range(env.n_trajectories)
        ]
        
        operator_scores = {
            k: np.random.randn() * 0.1 + 0.5
            for k in ['kinetic', 'potential', 'liquidity', 'ob', 'fvg']
        }
        
        state = env.reset(market_embedding, trajectories, operator_scores)
        episode_reward = 0
        wins = 0
        
        for step in range(env.max_steps):
            action, _, _ = agent.select_action(state, deterministic=deterministic)
            
            selected_trajectory = trajectories[action]
            market_state = {'current_price': 1.0}
            trade_result = env.simulate_trade_result(selected_trajectory, market_state)
            
            next_state, reward, done, _ = env.step(action, trade_result)
            episode_reward += reward
            
            if trade_result.win:
                wins += 1
            
            state = next_state
            if done:
                break
        
        episode_rewards.append(episode_reward)
        episode_wins.append(wins)
    
    return {
        'avg_reward': np.mean(episode_rewards),
        'std_reward': np.std(episode_rewards),
        'avg_wins': np.mean(episode_wins),
        'win_rate': np.mean([w / env.max_steps for w in episode_wins])
    }


if __name__ == "__main__":
    # Train on synthetic data
    history = train_synthetic()
    print("Training complete!")
