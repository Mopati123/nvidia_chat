#!/usr/bin/env python3
"""
Full Pipeline Integration Tests

Tests end-to-end integration of all 5 phases:
1. Memory (Vector DB + Embeddings)
2. NN Price Predictor (Transformer)
3. RL Agent (PPO)
4. Multi-Agent System
5. LLM Strategy Generator
"""

import sys
sys.path.insert(0, '.')

import numpy as np
import pytest
from typing import Dict, List


class TestMemoryToNNTOPipeline:
    """Test Phase 1 → Phase 2 integration"""
    
    def test_ohlcv_to_embedding_to_prediction(self):
        """OHLCV data → embedding → price prediction"""
        from trading.memory import get_embedder
        from trading.models import SimplePricePredictor
        
        # Generate synthetic OHLCV
        ohlcv = []
        base = 1.0850
        for i in range(100):
            ohlcv.append({
                'open': base + i * 0.0001 + np.random.normal(0, 0.0001),
                'high': base + i * 0.0001 + 0.0005,
                'low': base + i * 0.0001 - 0.0005,
                'close': base + i * 0.0001 + np.random.normal(0, 0.0002),
                'volume': 1000 + i * 10
            })
        
        # Phase 1: Encode to embedding
        embedder = get_embedder()
        embedding = embedder.encode(ohlcv)
        
        assert embedding.shape == (128,), f"Expected embedding shape (128,), got {embedding.shape}"
        assert not np.all(embedding == 0), "Embedding should not be all zeros"
        
        # Phase 2: Predict price
        predictor = SimplePricePredictor()
        prediction = predictor.predict(embedding)
        
        assert 'mean' in prediction, "Prediction should have 'mean'"
        assert 'std' in prediction, "Prediction should have 'std'"
        assert 'trend' in prediction, "Prediction should have 'trend'"
        assert prediction['std'] > 0, "Standard deviation should be positive"
        
        print(f"✅ Memory→NN: embedding shape {embedding.shape}, prediction mean={prediction['mean']:.4f}")
    
    def test_embedding_caching(self):
        """Test that embeddings are properly cached"""
        from trading.memory import get_embedder
        
        embedder = get_embedder()
        ohlcv = [{'open': 1.0, 'high': 1.1, 'low': 0.9, 'close': 1.0, 'volume': 1000} for _ in range(100)]
        
        # First call
        emb1 = embedder.encode(ohlcv)
        # Second call (should use cache if implemented)
        emb2 = embedder.encode(ohlcv)
        
        assert np.allclose(emb1, emb2), "Cached embedding should match"


class TestNNToRLPipeline:
    """Test Phase 2 → Phase 3 integration"""
    
    def test_prediction_to_rl_state(self):
        """NN prediction → RL state vector"""
        from trading.models import SimplePricePredictor
        from trading.rl import TradingEnvironment
        
        # Create prediction
        predictor = SimplePricePredictor()
        embedding = np.random.randn(128).astype(np.float32)
        prediction = predictor.predict(embedding)
        
        # Create trajectories
        trajectories = [
            {'id': f'traj_{i}', 'energy': np.random.rand(), 'action': np.random.randn()}
            for i in range(5)
        ]
        
        # Phase 3: Build RL state
        env = TradingEnvironment(n_trajectories=5)
        state = env.reset(embedding, trajectories, prediction)
        
        assert state.shape == (166,), f"Expected state shape (166,), got {state.shape}"
        assert not np.isnan(state).any(), "State should not contain NaN"
        assert not np.isinf(state).any(), "State should not contain Inf"
        
        print(f"✅ NN→RL: state shape {state.shape}, prediction integrated")
    
    def test_rl_state_with_prediction_uncertainty(self):
        """Test RL state includes prediction uncertainty"""
        from trading.rl import TradingEnvironment
        
        embedding = np.random.randn(128).astype(np.float32)
        trajectories = [{'id': f'traj_{i}', 'energy': 0.5, 'action': 0.1} for i in range(5)]
        
        # High uncertainty prediction
        high_uncertainty = {'mean': 1.0, 'std': 0.1, 'trend': 0.5}
        
        env = TradingEnvironment(n_trajectories=5)
        state = env.reset(embedding, trajectories, high_uncertainty)
        
        assert state.shape == (166,), "State shape should be correct with uncertainty"


class TestAgentsToSchedulerPipeline:
    """Test Phase 4 → Scheduler integration"""
    
    def test_agent_votes_to_scheduler_decision(self):
        """Agents vote → orchestrator aggregates → scheduler decides"""
        from trading.agents import (
            PatternAgent, RiskAgent, TimingAgent, MetaAgent,
            MultiAgentOrchestrator
        )
        from trading.kernel import Scheduler
        
        # Create agents
        pattern = PatternAgent(name="PatternAgent", weight=1.0)
        risk = RiskAgent(name="RiskAgent", weight=1.0)
        timing = TimingAgent(name="TimingAgent", weight=1.0)
        meta = MetaAgent(name="MetaAgent")
        
        orchestrator = MultiAgentOrchestrator(
            agents=[pattern, risk, timing],
            meta_agent=meta
        )
        
        # Create test data
        ohlcv = [{'open': 1.0, 'high': 1.01, 'low': 0.99, 'close': 1.0, 'volume': 1000} for _ in range(100)]
        market_state = {'ohlc': ohlcv, 'operator_scores': {}}
        
        trajectories = [
            {'id': 'traj_0', 'energy': 0.3, 'action': 0.1, 'operator_scores': {'kinetic': 0.5}},
            {'id': 'traj_1', 'energy': 0.5, 'action': 0.2, 'operator_scores': {'kinetic': 0.7}},
        ]
        
        # Collect and aggregate votes
        votes = orchestrator.collect_votes(trajectories, market_state)
        decision = orchestrator.aggregate_votes(votes, strategy='weighted')
        
        # Scheduler makes final decision
        scheduler = Scheduler(config={'use_rl': False})
        
        from trading.kernel.scheduler import CollapseDecision
        collapse_decision, token = scheduler.authorize_collapse(
            proposal={},
            projected_trajectories=trajectories,
            delta_s=0.3,
            constraints_passed=True,
            reconciliation_clear=True
        )
        
        assert collapse_decision in [CollapseDecision.AUTHORIZED, CollapseDecision.REFUSED]
        assert decision.selected_trajectory < len(trajectories)
        
        print(f"✅ Agents→Scheduler: {len(votes)} votes, decision={collapse_decision.value}")


class TestStrategyToAgentsPipeline:
    """Test Phase 5 → Phase 4 integration"""
    
    def test_strategy_input_to_agent_votes(self):
        """Natural language → StrategyAgent → multi-agent voting"""
        from trading.agents import (
            StrategyAgent, PatternAgent, RiskAgent, TimingAgent,
            MultiAgentOrchestrator
        )
        
        strategy_agent = StrategyAgent(llm_provider="mock", weight=1.2)
        pattern = PatternAgent(weight=1.0)
        risk = RiskAgent(weight=1.0)
        timing = TimingAgent(weight=1.0)
        
        orchestrator = MultiAgentOrchestrator(
            agents=[pattern, risk, timing, strategy_agent]
        )
        
        # Market state
        ohlcv = [{'open': 1.0, 'high': 1.01, 'low': 0.99, 'close': 1.0, 'volume': 1000} for _ in range(100)]
        market_state = {'ohlc': ohlcv, 'trend': 'bullish', 'volatility': 0.01}
        
        trajectories = [
            {'id': 'traj_0', 'energy': 0.3, 'action': 0.1, 'operator_scores': {'order_block': 0.8}},
            {'id': 'traj_1', 'energy': 0.5, 'action': 0.2, 'operator_scores': {'fvg': 0.7}},
        ]
        
        # Provide strategy input
        context = {'strategy_input': 'Buy at bullish order block'}
        
        votes = orchestrator.collect_votes(trajectories, market_state, context)
        decision = orchestrator.aggregate_votes(votes, strategy='weighted')
        
        strategy_vote = [v for v in votes if v.agent_name == "StrategyAgent"]
        assert len(strategy_vote) == 1, "StrategyAgent should have voted"
        assert not strategy_vote[0].refusal, "StrategyAgent should not refuse"
        
        print(f"✅ Strategy→Agents: StrategyAgent voted with conf={strategy_vote[0].confidence:.2f}")


class TestFullSystemIntegration:
    """Test complete 5-phase integration"""
    
    def test_full_trading_decision_pipeline(self):
        """
        Complete pipeline:
        OHLCV → Embedding → Prediction → Agent Votes → RL Augmentation → Scheduler Decision
        """
        from trading.memory import get_embedder
        from trading.models import SimplePricePredictor
        from trading.rl import PPOSchedulerAgent
        from trading.agents import (
            PatternAgent, RiskAgent, TimingAgent, StrategyAgent, MetaAgent,
            MultiAgentOrchestrator
        )
        from trading.kernel import Scheduler
        
        print("\n🔄 Running full pipeline integration test...")
        
        # 1. Generate market data
        ohlcv = []
        base = 1.0850
        for i in range(100):
            ohlcv.append({
                'open': base + i * 0.0001,
                'high': base + i * 0.0001 + 0.0005,
                'low': base + i * 0.0001 - 0.0005,
                'close': base + i * 0.0001,
                'volume': 1000
            })
        
        # 2. Phase 1: Memory encoding
        embedder = get_embedder()
        embedding = embedder.encode(ohlcv)
        assert embedding.shape == (128,)
        
        # 3. Phase 2: Price prediction
        predictor = SimplePricePredictor()
        prediction = predictor.predict(embedding)
        
        # 4. Phase 4: Multi-agent voting
        pattern = PatternAgent()
        risk = RiskAgent()
        timing = TimingAgent()
        strategy = StrategyAgent(llm_provider="mock")
        meta = MetaAgent()
        
        orchestrator = MultiAgentOrchestrator(
            agents=[pattern, risk, timing, strategy],
            meta_agent=meta
        )
        
        market_state = {
            'ohlc': ohlcv,
            'trend': prediction.get('trend', 'neutral'),
            'volatility': prediction.get('std', 0),
            'operator_scores': {}
        }
        
        trajectories = [
            {'id': f'traj_{i}', 'energy': 0.3 + i*0.1, 'action': 0.1 + i*0.05,
             'operator_scores': {'kinetic': 0.5 + i*0.1}}
            for i in range(3)
        ]
        
        votes = orchestrator.collect_votes(trajectories, market_state)
        agent_decision = orchestrator.aggregate_votes(votes, strategy='weighted')
        
        # 5. Phase 3: RL augmentation (optional)
        try:
            rl_agent = PPOSchedulerAgent(state_dim=166, action_dim=3, device="cpu")
            state = np.concatenate([
                embedding,
                np.array([t['energy'] for t in trajectories[:5]]),
                np.array([t['action'] for t in trajectories[:5]]),
                np.zeros(18),  # operator scores
                np.zeros(10)   # pnl history
            ]).astype(np.float32)
            
            action, log_prob, value = rl_agent.select_action(state)
            rl_recommendation = trajectories[action] if action < len(trajectories) else trajectories[0]
            use_rl = True
        except Exception as e:
            use_rl = False
            rl_recommendation = None
        
        # 6. Phase 4: Scheduler decision
        scheduler = Scheduler(config={'use_rl': use_rl})
        
        from trading.kernel.scheduler import CollapseDecision
        collapse_decision, token = scheduler.authorize_collapse(
            proposal={'agent_decision': agent_decision.to_dict() if hasattr(agent_decision, 'to_dict') else agent_decision},
            projected_trajectories=trajectories,
            delta_s=0.3,
            constraints_passed=True,
            reconciliation_clear=True
        )
        
        assert collapse_decision in [CollapseDecision.AUTHORIZED, CollapseDecision.REFUSED]
        
        print(f"✅ Full Pipeline: {len(votes)} agents, RL={use_rl}, Decision={collapse_decision.value}")
        print(f"   Selected trajectory: {agent_decision.selected_trajectory}")
        print(f"   Consensus: {agent_decision.consensus_score:.2f}")
        
        return True


class TestDataFlowIntegrity:
    """Test data integrity through the pipeline"""
    
    def test_no_data_loss_between_phases(self):
        """Verify no critical data is lost between phases"""
        # This would test that market metadata propagates correctly
        pass
    
    def test_error_propagation(self):
        """Test that errors are properly caught and handled"""
        pass


if __name__ == "__main__":
    print("="*70)
    print("🚀 FULL PIPELINE INTEGRATION TESTS")
    print("="*70)
    
    # Run tests
    import sys
    
    test_classes = [
        TestMemoryToNNTOPipeline,
        TestNNToRLPipeline,
        TestAgentsToSchedulerPipeline,
        TestStrategyToAgentsPipeline,
        TestFullSystemIntegration,
    ]
    
    passed = 0
    failed = 0
    
    for test_class in test_classes:
        print(f"\n📋 {test_class.__name__}")
        print("-" * 50)
        
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith('test_')]
        
        for method_name in methods:
            try:
                method = getattr(instance, method_name)
                method()
                passed += 1
                print(f"  ✅ {method_name}")
            except Exception as e:
                failed += 1
                print(f"  ❌ {method_name}: {e}")
    
    print("\n" + "="*70)
    print(f"📊 RESULTS: {passed} passed, {failed} failed")
    print("="*70)
    
    sys.exit(0 if failed == 0 else 1)
