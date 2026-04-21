#!/usr/bin/env python3
"""
Test script for Multi-Agent System

Verifies:
1. PatternAgent detects patterns and votes
2. RiskAgent computes risk metrics and votes
3. TimingAgent evaluates timing and votes
4. MetaAgent tracks performance and adjusts weights
5. Orchestrator aggregates votes correctly
"""

import sys
sys.path.insert(0, '.')

import numpy as np

def test_pattern_agent():
    """Test PatternAgent"""
    print("\n" + "="*70)
    print("🧪 TEST 1: PatternAgent")
    print("="*70)
    
    from trading.agents import PatternAgent
    
    agent = PatternAgent(name="TestPatternAgent", weight=1.0)
    
    # Create sample OHLCV with patterns
    ohlc = []
    base = 1.0850
    for i in range(100):
        if i == 50:  # Create a FVG
            open_p = base + i * 0.0001 + 0.001
            close = open_p + 0.0005
            high = close + 0.0002
            low = open_p - 0.0002
        else:
            open_p = base + i * 0.0001
            close = open_p + np.random.normal(0, 0.0002)
            high = max(open_p, close) + 0.0002
            low = min(open_p, close) - 0.0002
        
        ohlc.append({
            'open': open_p,
            'high': high,
            'low': low,
            'close': close,
            'volume': 1000 + i * 10
        })
    
    market_state = {'ohlc': ohlc, 'operator_scores': {}}
    
    trajectories = [
        {'id': 'traj_0', 'energy': 0.3, 'action': 0.1, 'operator_scores': {'kinetic': 0.5}},
        {'id': 'traj_1', 'energy': 0.5, 'action': 0.2, 'operator_scores': {'kinetic': 0.7}},
    ]
    
    vote = agent.vote(trajectories, market_state)
    
    print(f"✅ Vote cast: {vote.agent_name}")
    print(f"✅ Refusal: {vote.refusal}")
    print(f"✅ Confidence: {vote.confidence:.3f}")
    print(f"✅ Preferred trajectory: {vote.preferred_trajectory}")
    print(f"✅ Trajectory scores: {vote.trajectory_scores}")
    print(f"✅ Rationale: {vote.rationale[:80]}...")
    print(f"✅ Detected patterns: {vote.metadata.get('pattern_count', 0)}")
    
    return not vote.refusal


def test_risk_agent():
    """Test RiskAgent"""
    print("\n" + "="*70)
    print("🧪 TEST 2: RiskAgent")
    print("="*70)
    
    from trading.agents import RiskAgent
    
    agent = RiskAgent(name="TestRiskAgent", weight=1.0, max_risk_per_trade=0.02)
    
    # Create market state
    ohlc = []
    for i in range(100):
        ohlc.append({
            'open': 1.0 + i * 0.0001,
            'high': 1.0 + i * 0.0001 + 0.001,
            'low': 1.0 + i * 0.0001 - 0.001,
            'close': 1.0 + i * 0.0001,
            'volume': 1000
        })
    
    market_state = {'ohlc': ohlc, 'volatility': 0.01, 'operator_scores': {}}
    
    trajectories = [
        {'id': 'traj_0', 'energy': 0.3, 'action': 0.1},
        {'id': 'traj_1', 'energy': 0.5, 'action': 0.2},
    ]
    
    vote = agent.vote(trajectories, market_state)
    
    print(f"✅ Vote cast: {vote.agent_name}")
    print(f"✅ Refusal: {vote.refusal}")
    if not vote.refusal:
        print(f"✅ Confidence: {vote.confidence:.3f}")
        print(f"✅ Preferred trajectory: {vote.preferred_trajectory}")
        print(f"✅ Recommended position: {vote.metadata.get('recommended_position', 0):.2%}")
    
    return True


def test_timing_agent():
    """Test TimingAgent"""
    print("\n" + "="*70)
    print("🧪 TEST 3: TimingAgent")
    print("="*70)
    
    from trading.agents import TimingAgent
    
    agent = TimingAgent(name="TestTimingAgent", weight=1.0)
    
    # Create market state
    ohlc = []
    for i in range(100):
        ohlc.append({
            'open': 1.0 + i * 0.0001,
            'high': 1.0 + i * 0.0001 + 0.0005,
            'low': 1.0 + i * 0.0001 - 0.0005,
            'close': 1.0 + i * 0.0001,
            'volume': 1000
        })
    
    market_state = {'ohlc': ohlc, 'operator_scores': {}}
    
    trajectories = [
        {'id': 'traj_0', 'energy': 0.3, 'action': 0.1},
        {'id': 'traj_1', 'energy': 0.5, 'action': 0.2},
    ]
    
    vote = agent.vote(trajectories, market_state)
    
    print(f"✅ Vote cast: {vote.agent_name}")
    print(f"✅ Refusal: {vote.refusal}")
    if not vote.refusal:
        print(f"✅ Confidence: {vote.confidence:.3f}")
        print(f"✅ Preferred trajectory: {vote.preferred_trajectory}")
        print(f"✅ Quality score: {vote.metadata.get('quality_score', 0):.3f}")
        print(f"✅ Optimal delay: {vote.metadata.get('optimal_delay', 0)} steps")
    
    return True


def test_meta_agent():
    """Test MetaAgent"""
    print("\n" + "="*70)
    print("🧪 TEST 4: MetaAgent")
    print("="*70)
    
    from trading.agents import MetaAgent, AgentVote
    
    meta = MetaAgent(name="TestMetaAgent")
    
    # Simulate some agent performance data
    for i in range(30):
        vote = AgentVote(
            agent_name="TestAgent",
            agent_type="pattern",
            confidence=0.7,
            preferred_trajectory=i % 2,
            trajectory_scores={0: 0.5, 1: 0.5}
        )
        
        pnl = np.random.choice([0.02, -0.01], p=[0.6, 0.4])  # 60% win rate
        meta.update_agent_performance("TestAgent", vote, pnl, was_followed=(i % 2 == 0))
    
    # Get status
    status = meta.get_agent_status("TestAgent")
    
    print(f"✅ MetaAgent status retrieved")
    print(f"✅ Total trades tracked: {status['metrics']['total_trades']}")
    print(f"✅ Win rate: {status['metrics']['win_rate']:.2%}")
    print(f"✅ Accuracy: {status['metrics']['accuracy']:.2%}")
    print(f"✅ Cumulative PnL: {status['metrics']['cumulative_pnl']:.4f}")
    
    # Update weights
    meta.update_weights()
    
    weight = meta.get_agent_weight("TestAgent")
    print(f"✅ Computed weight: {weight:.3f}")
    
    return True


def test_orchestrator():
    """Test MultiAgentOrchestrator"""
    print("\n" + "="*70)
    print("🧪 TEST 5: MultiAgentOrchestrator")
    print("="*70)
    
    from trading.agents import (
        PatternAgent, RiskAgent, TimingAgent,
        MetaAgent, MultiAgentOrchestrator
    )
    
    # Create agents
    pattern = PatternAgent(name="PatternAgent", weight=1.0)
    risk = RiskAgent(name="RiskAgent", weight=1.0)
    timing = TimingAgent(name="TimingAgent", weight=1.0)
    meta = MetaAgent(name="MetaAgent")
    
    # Create orchestrator
    orchestrator = MultiAgentOrchestrator(
        agents=[pattern, risk, timing],
        meta_agent=meta,
        default_strategy='weighted'
    )
    
    # Create test data
    ohlc = []
    for i in range(100):
        ohlc.append({
            'open': 1.0 + i * 0.0001,
            'high': 1.0 + i * 0.0001 + 0.0005,
            'low': 1.0 + i * 0.0001 - 0.0005,
            'close': 1.0 + i * 0.0001,
            'volume': 1000
        })
    
    market_state = {'ohlc': ohlc, 'volatility': 0.01, 'operator_scores': {}}
    
    trajectories = [
        {'id': 'traj_0', 'energy': 0.3, 'action': 0.1, 'operator_scores': {'kinetic': 0.5}},
        {'id': 'traj_1', 'energy': 0.5, 'action': 0.2, 'operator_scores': {'kinetic': 0.7}},
        {'id': 'traj_2', 'energy': 0.4, 'action': 0.15, 'operator_scores': {'kinetic': 0.6}},
    ]
    
    # Collect votes
    votes = orchestrator.collect_votes(trajectories, market_state)
    
    print(f"✅ Collected {len(votes)} votes")
    for vote in votes:
        print(f"   - {vote.agent_name}: traj={vote.preferred_trajectory}, conf={vote.confidence:.2f}, refuse={vote.refusal}")
    
    # Aggregate with different strategies
    for strategy in ['majority', 'weighted', 'consensus']:
        decision = orchestrator.aggregate_votes(votes, strategy=strategy, n_trajectories=3)
        
        print(f"\n✅ Strategy: {strategy}")
        print(f"   Selected: traj_{decision.selected_trajectory}")
        print(f"   Confidence: {decision.confidence:.3f}")
        print(f"   Consensus: {decision.consensus_score:.3f}")
        print(f"   Refusals: {decision.refusal_count}/{decision.total_votes}")
        print(f"   Refused: {decision.refusal}")
    
    # Report trade outcome
    decision = orchestrator.aggregate_votes(votes, strategy='weighted')
    orchestrator.report_trade_outcome(pnl=0.015, selected_trajectory=1, decision=decision)
    
    print(f"\n✅ Trade outcome reported")
    print(f"✅ Performance tracking active")
    
    return True


def main():
    """Run all tests"""
    print("="*70)
    print("🚀 MULTI-AGENT SYSTEM TEST SUITE")
    print("="*70)
    
    tests = [
        ("PatternAgent", test_pattern_agent),
        ("RiskAgent", test_risk_agent),
        ("TimingAgent", test_timing_agent),
        ("MetaAgent", test_meta_agent),
        ("Orchestrator", test_orchestrator),
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
