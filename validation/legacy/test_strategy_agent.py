#!/usr/bin/env python3
"""
Test script for LLM Strategy Agent

Verifies:
1. Natural language parsing
2. LLM strategy generation (mock)
3. Strategy proposal structure
4. Multi-agent voting integration
"""

import sys
sys.path.insert(0, '.')

def test_strategy_parsing():
    """Test natural language parsing"""
    print("\n" + "="*70)
    print("🧪 TEST 1: Strategy Parsing")
    print("="*70)
    
    from trading.agents import StrategyAgent
    
    agent = StrategyAgent(llm_provider="mock")
    
    test_inputs = [
        "Buy EURUSD at bullish order block targeting 1.09 with 1% risk",
        "Short GBPUSD when price sweeps liquidity above 1.27",
        "Long BTCUSD at fair value gap with 2:1 R:R and 2% risk",
        "Sell USDJPY on break of structure with stop above recent high",
    ]
    
    for i, inp in enumerate(test_inputs, 1):
        intent = agent.parse_strategy_input(inp)
        
        print(f"\n✅ Input {i}: \"{inp[:50]}...\"")
        print(f"   Action: {intent.action}")
        print(f"   Asset: {intent.asset or 'Not detected'}")
        print(f"   Timeframe: {intent.timeframe or 'Not specified'}")
        print(f"   Entry conditions: {intent.entry_conditions or 'None'}")
        print(f"   Risk: {intent.risk_constraints}")
        print(f"   Parse confidence: {intent.metadata.get('parse_confidence', 0):.2f}")
    
    return True


def test_strategy_generation():
    """Test strategy generation"""
    print("\n" + "="*70)
    print("🧪 TEST 2: Strategy Generation")
    print("="*70)
    
    from trading.agents import StrategyAgent
    
    agent = StrategyAgent(llm_provider="mock")
    
    # Create market state
    ohlc = []
    for i in range(50):
        ohlc.append({
            'open': 1.0850 + i * 0.0001,
            'high': 1.0855 + i * 0.0001,
            'low': 1.0845 + i * 0.0001,
            'close': 1.0852 + i * 0.0001,
            'volume': 1000
        })
    
    market_state = {
        'ohlc': ohlc,
        'trend': 'bullish',
        'volatility': 0.01,
        'current_price': 1.0877,
        'symbol': 'EURUSD'
    }
    
    # Parse intent
    intent = agent.parse_strategy_input(
        "Buy EURUSD at bullish order block targeting recent high"
    )
    
    # Generate strategy
    proposal = agent.generate_strategy(market_state, intent)
    
    print(f"✅ Strategy generated:")
    print(f"   Action: {proposal.intent.action}")
    print(f"   Entry: {proposal.parameters.get('entry_price', 'N/A')}")
    print(f"   Stop: {proposal.parameters.get('stop_loss', 'N/A')}")
    print(f"   Target: {proposal.parameters.get('take_profit', 'N/A')}")
    print(f"   Position size: {proposal.parameters.get('position_size', 'N/A')}")
    print(f"   Confidence: {proposal.confidence:.2f}")
    print(f"   Rationale: {proposal.reasoning[:60]}...")
    print(f"   Operators: {proposal.trajectory_filters.get('preferred_operators', [])}")
    print(f"   LLM used: {proposal.metadata.get('llm_used', False)}")
    
    return True


def test_strategy_voting():
    """Test strategy agent voting"""
    print("\n" + "="*70)
    print("🧪 TEST 3: Strategy Agent Voting")
    print("="*70)
    
    from trading.agents import StrategyAgent
    
    agent = StrategyAgent(llm_provider="mock")
    
    # Create market state and trajectories
    ohlc = []
    for i in range(50):
        ohlc.append({
            'open': 1.0850 + i * 0.0001,
            'high': 1.0855 + i * 0.0001,
            'low': 1.0845 + i * 0.0001,
            'close': 1.0852 + i * 0.0001,
            'volume': 1000
        })
    
    market_state = {
        'ohlc': ohlc,
        'trend': 'bullish',
        'volatility': 0.01,
        'symbol': 'EURUSD'
    }
    
    trajectories = [
        {'id': 'traj_0', 'energy': 0.2, 'action': 0.05, 'operator_scores': {'kinetic': 0.3}},
        {'id': 'traj_1', 'energy': 0.5, 'action': 0.15, 'operator_scores': {'kinetic': 0.7, 'order_block': 0.8}},
        {'id': 'traj_2', 'energy': 0.4, 'action': -0.1, 'operator_scores': {'kinetic': 0.5}},
    ]
    
    context = {'strategy_input': 'Buy EURUSD at order block'}
    
    vote = agent.vote(trajectories, market_state, context)
    
    print(f"✅ Vote cast by {vote.agent_name}")
    print(f"   Refusal: {vote.refusal}")
    print(f"   Confidence: {vote.confidence:.2f}")
    print(f"   Preferred trajectory: {vote.preferred_trajectory}")
    print(f"   Trajectory scores: {vote.trajectory_scores}")
    print(f"   Rationale: {vote.rationale[:70]}...")
    print(f"   LLM used: {vote.metadata.get('llm_used', False)}")
    
    return not vote.refusal


def test_multi_agent_with_strategy():
    """Test full multi-agent system including StrategyAgent"""
    print("\n" + "="*70)
    print("🧪 TEST 4: Multi-Agent with StrategyAgent")
    print("="*70)
    
    from trading.agents import (
        PatternAgent, RiskAgent, TimingAgent,
        StrategyAgent, MetaAgent, MultiAgentOrchestrator
    )
    
    # Create all agents
    pattern = PatternAgent(name="PatternAgent", weight=1.0)
    risk = RiskAgent(name="RiskAgent", weight=1.0)
    timing = TimingAgent(name="TimingAgent", weight=1.0)
    strategy = StrategyAgent(name="StrategyAgent", weight=1.2, llm_provider="mock")  # Slightly higher weight
    meta = MetaAgent(name="MetaAgent")
    
    # Create orchestrator with StrategyAgent
    orchestrator = MultiAgentOrchestrator(
        agents=[pattern, risk, timing, strategy],
        meta_agent=meta,
        default_strategy='weighted'
    )
    
    print(f"✅ Orchestrator created with {len(orchestrator.agents)} agents:")
    for agent in orchestrator.agents:
        print(f"   - {agent.name} ({agent.agent_type}, weight={agent.weight})")
    
    # Create test data
    ohlc = []
    for i in range(100):
        ohlc.append({
            'open': 1.0850 + i * 0.0001,
            'high': 1.0855 + i * 0.0001,
            'low': 1.0845 + i * 0.0001,
            'close': 1.0852 + i * 0.0001,
            'volume': 1000
        })
    
    market_state = {
        'ohlc': ohlc,
        'trend': 'bullish',
        'volatility': 0.01,
        'symbol': 'EURUSD',
        'current_price': 1.0900
    }
    
    trajectories = [
        {'id': 'traj_0', 'energy': 0.2, 'action': 0.05, 'operator_scores': {'kinetic': 0.3}},
        {'id': 'traj_1', 'energy': 0.6, 'action': 0.20, 'operator_scores': {'kinetic': 0.8, 'order_block': 0.9}},
        {'id': 'traj_2', 'energy': 0.4, 'action': 0.15, 'operator_scores': {'kinetic': 0.5, 'fvg': 0.7}},
    ]
    
    # Collect votes with strategy context
    context = {'strategy_input': 'Buy EURUSD at bullish order block'}
    votes = orchestrator.collect_votes(trajectories, market_state, context)
    
    print(f"\n✅ Collected {len(votes)} votes:")
    for vote in votes:
        print(f"   - {vote.agent_name}: traj={vote.preferred_trajectory}, "
              f"conf={vote.confidence:.2f}, refuse={vote.refusal}")
    
    # Aggregate
    decision = orchestrator.aggregate_votes(votes, strategy='weighted')
    
    print(f"\n✅ Aggregated decision:")
    print(f"   Selected trajectory: traj_{decision.selected_trajectory}")
    print(f"   Confidence: {decision.confidence:.2f}")
    print(f"   Consensus: {decision.consensus_score:.2f}")
    print(f"   Refusals: {decision.refusal_count}/{decision.total_votes}")
    
    return True


def test_llm_interface_factory():
    """Test LLM interface factory"""
    print("\n" + "="*70)
    print("🧪 TEST 5: LLM Interface Factory")
    print("="*70)
    
    from trading.agents import LLMInterfaceFactory, get_default_interface
    
    # Test mock interface
    mock = LLMInterfaceFactory.create_interface("mock")
    print(f"✅ Mock interface: {type(mock).__name__}")
    print(f"   Available: {mock.is_available()}")
    
    # Test auto interface
    auto = get_default_interface()
    print(f"\n✅ Auto interface: {type(auto).__name__}")
    print(f"   Available: {auto.is_available()}")
    
    # Test strategy generation with mock
    from trading.agents import StrategyIntent
    
    intent = StrategyIntent(
        action="buy",
        asset="EURUSD",
        entry_conditions=["at bullish order block"],
        raw_input="Test input"
    )
    
    market_desc = "EURUSD at 1.0850, bullish trend, low volatility"
    proposal = mock.generate_strategy(market_desc, intent, {})
    
    print(f"\n✅ Mock generation:")
    print(f"   Entry: {proposal.parameters.get('entry_price')}")
    print(f"   Stop: {proposal.parameters.get('stop_loss')}")
    print(f"   Confidence: {proposal.confidence}")
    print(f"   Source: {proposal.metadata.get('source')}")
    
    return True


def main():
    """Run all tests"""
    print("="*70)
    print("🚀 LLM STRATEGY AGENT TEST SUITE")
    print("="*70)
    
    tests = [
        ("Strategy Parsing", test_strategy_parsing),
        ("Strategy Generation", test_strategy_generation),
        ("Strategy Voting", test_strategy_voting),
        ("Multi-Agent Integration", test_multi_agent_with_strategy),
        ("LLM Interface Factory", test_llm_interface_factory),
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
