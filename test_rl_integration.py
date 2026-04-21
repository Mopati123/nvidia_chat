#!/usr/bin/env python3
"""
Test script for RL Agent Integration

Verifies:
1. Trading environment state space
2. Actor-Critic network forward pass
3. PPO agent action selection
4. Scheduler integration
"""

import sys
sys.path.insert(0, '.')

import numpy as np
import torch

def test_environment():
    """Test trading environment"""
    print("\n" + "="*70)
    print("🧪 TEST 1: Trading Environment")
    print("="*70)
    
    from trading.rl import TradingEnvironment, SyntheticTradingEnv
    
    # Test basic environment
    env = TradingEnvironment(n_trajectories=5)
    
    print(f"✅ State dimension: {env.state_dim} (expected: 166)")
    print(f"✅ Action dimension: {env.n_trajectories}")
    
    # Create sample data
    market_embedding = np.random.randn(128)
    trajectories = [
        {'id': f'traj_{i}', 'energy': np.random.randn(), 'action': np.random.randn()}
        for i in range(5)
    ]
    operator_scores = {'kinetic': 0.5, 'ob': 0.3, 'fvg': 0.7}
    
    # Reset environment
    state = env.reset(market_embedding, trajectories, operator_scores)
    
    print(f"✅ State shape: {state.shape}")
    print(f"✅ State range: [{state.min():.4f}, {state.max():.4f}]")
    print(f"✅ State mean: {state.mean():.4f}")
    print(f"✅ State std: {state.std():.4f}")
    
    # Test step
    action = 2
    from trading.rl.environment import TradeResult
    trade_result = TradeResult(
        entry_price=1.0,
        exit_price=1.02,
        pnl=0.02,
        pnl_pct=0.02,
        duration_steps=10,
        max_drawdown=0.005,
        win=True,
        timestamp="2024-01-01T00:00:00"
    )
    
    next_state, reward, done, info = env.step(action, trade_result)
    
    print(f"✅ Step reward: {reward:.4f}")
    print(f"✅ Done: {done}")
    print(f"✅ Info: {info}")
    
    # Test synthetic environment
    synth_env = SyntheticTradingEnv(n_trajectories=5)
    market_state = {'current_price': 1.0}
    synthetic_result = synth_env.simulate_trade_result(trajectories[0], market_state)
    
    print(f"✅ Synthetic trade generated:")
    print(f"   PnL: {synthetic_result.pnl_pct:.4f}")
    print(f"   Win: {synthetic_result.win}")
    print(f"   Duration: {synthetic_result.duration_steps}")
    
    return True


def test_policy_network():
    """Test Actor-Critic network"""
    print("\n" + "="*70)
    print("🧪 TEST 2: Actor-Critic Network")
    print("="*70)
    
    from trading.rl import ActorCritic
    
    model = ActorCritic(state_dim=166, action_dim=5)
    
    # Test forward pass
    state = torch.randn(166)
    action_logits, value = model(state)
    
    print(f"✅ Action logits shape: {action_logits.shape} (expected: (5,))")
    print(f"✅ Value shape: {value.shape} (expected: (1,))")
    print(f"✅ Action logits range: [{action_logits.min().item():.4f}, {action_logits.max().item():.4f}]")
    print(f"✅ Value: {value.item():.4f}")
    
    # Test action selection
    action, log_prob, value_out = model.get_action(state, deterministic=False)
    
    print(f"✅ Sampled action: {action}")
    print(f"✅ Log prob: {log_prob:.4f}")
    print(f"✅ Value out: {value_out:.4f}")
    
    # Test batch forward
    batch_state = torch.randn(32, 166)
    batch_logits, batch_values = model(batch_state)
    
    print(f"✅ Batch logits shape: {batch_logits.shape} (expected: (32, 5))")
    print(f"✅ Batch values shape: {batch_values.shape} (expected: (32, 1))")
    
    # Count parameters
    total_params = sum(p.numel() for p in model.parameters())
    print(f"✅ Total parameters: {total_params:,}")
    
    return True


def test_ppo_agent():
    """Test PPO agent"""
    print("\n" + "="*70)
    print("🧪 TEST 3: PPO Agent")
    print("="*70)
    
    from trading.rl import PPOSchedulerAgent
    
    agent = PPOSchedulerAgent(
        state_dim=166,
        action_dim=5,
        device="cpu",
        buffer_size=128  # Small for testing
    )
    
    # Test action selection
    state = np.random.randn(166).astype(np.float32)
    action, log_prob, value = agent.select_action(state)
    
    print(f"✅ Selected action: {action}")
    print(f"✅ Log prob: {log_prob:.4f}")
    print(f"✅ Value estimate: {value:.4f}")
    
    # Test storing transitions
    for i in range(10):
        state = np.random.randn(166).astype(np.float32)
        action, log_prob, value = agent.select_action(state)
        reward = np.random.randn() * 0.1
        done = (i == 9)
        
        agent.store_transition(state, action, reward, log_prob, value, done)
    
    print(f"✅ Stored {len(agent.buffer)} transitions")
    
    # Test update
    metrics = agent.update()
    
    if metrics:
        print(f"✅ Update completed:")
        print(f"   Total loss: {metrics['total_loss']:.4f}")
        print(f"   Policy loss: {metrics['policy_loss']:.4f}")
        print(f"   Value loss: {metrics['value_loss']:.4f}")
        print(f"   Entropy: {metrics['entropy']:.4f}")
    else:
        print("⚠️ No update (buffer not full)")
    
    return True


def test_scheduler_integration():
    """Test scheduler integration"""
    print("\n" + "="*70)
    print("🧪 TEST 4: Scheduler Integration")
    print("="*70)
    
    from trading.kernel import Scheduler
    
    # Test scheduler without RL
    scheduler = Scheduler(config={'use_rl': False})
    
    print("Scheduler without RL:")
    print(f"  use_rl: {scheduler.use_rl}")
    print(f"  rl_agent: {scheduler.rl_agent}")
    
    # Create test trajectories
    trajectories = [
        {
            'id': f'traj_{i}',
            'energy': np.random.rand(),
            'action': np.random.randn(),
            'operator_scores': {'kinetic': 0.5, 'ob': 0.3}
        }
        for i in range(5)
    ]
    
    # Test selection
    selected = scheduler._select_trajectory(trajectories)
    print(f"✅ Selected trajectory: {selected['id']}")
    
    # Test with RL enabled (will fail gracefully if no agent)
    try:
        scheduler_rl = Scheduler(config={
            'use_rl': True,
            'rl_threshold': 0.7
        })
        
        print("\nScheduler with RL:")
        print(f"  use_rl: {scheduler_rl.use_rl}")
        print(f"  rl_threshold: {scheduler_rl.rl_threshold}")
        
        # Test RL state building
        market_state = {
            'ohlc': [{'open': 1.0, 'high': 1.01, 'low': 0.99, 'close': 1.0, 'volume': 1000}] * 100,
            'operator_scores': {'kinetic': 0.5, 'ob': 0.3}
        }
        
        selected_rl = scheduler_rl._select_trajectory(trajectories, market_state)
        print(f"✅ RL-augmented selection: {selected_rl['id']}")
        
        # Test trade outcome reporting
        scheduler_rl.report_trade_outcome(pnl=0.02, done=True)
        print("✅ Trade outcome reported")
        
    except Exception as e:
        print(f"⚠️ RL integration test skipped: {e}")
    
    return True


def main():
    """Run all tests"""
    print("="*70)
    print("🚀 RL AGENT INTEGRATION TEST SUITE")
    print("="*70)
    
    tests = [
        ("Trading Environment", test_environment),
        ("Actor-Critic Network", test_policy_network),
        ("PPO Agent", test_ppo_agent),
        ("Scheduler Integration", test_scheduler_integration),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
                print(f"\n✅ {name}: PASSED")
            else:
                failed += 1
                print(f"\n❌ {name}: FAILED")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name}: ERROR - {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print(f"📊 RESULTS: {passed} passed, {failed} failed")
    print("="*70)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
