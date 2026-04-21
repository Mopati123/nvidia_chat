# Quantum-Inspired Trading System

A sophisticated, multi-phase trading framework combining quantum physics concepts with modern AI/ML techniques.

## 🎯 Overview

This system implements a **5-phase AI-enhanced trading architecture**:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Phase 1   │───▶│   Phase 2   │───▶│   Phase 3   │───▶│   Phase 4   │───▶│   Phase 5   │
│    Memory   │    │      NN     │    │      RL     │    │   Agents    │    │     LLM     │
│  (VectorDB) │    │(Transformer)│    │    (PPO)    │    │ (Multi)     │    │ (Strategy)  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

**Key Features:**
- 🔮 **Quantum-inspired path integral** trajectory generation
- 🧠 **Neural network** price prediction with uncertainty quantification
- 🤖 **RL agent** (PPO) for optimal trade timing
- 🎭 **Multi-agent system** with specialized agents and weighted voting
- 💬 **LLM-powered** natural language strategy generation

## 🚀 Quick Start (5 Minutes)

### Installation

```bash
# Clone repository
git clone <repository-url>
cd quantum-trading-system

# Install dependencies
pip install -r requirements.txt

# Optional: Install PyTorch for neural components
pip install torch

# Optional: Install ChromaDB for vector storage
pip install chromadb

# Optional: Install OpenAI for LLM features
pip install openai
```

### Basic Usage

```python
from trading.memory import get_embedder
from trading.models import PricePredictor
from trading.agents import PatternAgent, RiskAgent, MultiAgentOrchestrator
from trading.kernel import Scheduler

# 1. Prepare market data
ohlcv = [
    {'open': 1.0850, 'high': 1.0855, 'low': 1.0845, 'close': 1.0852, 'volume': 1000}
    for _ in range(100)
]

# 2. Generate embedding
embedder = get_embedder()
embedding = embedder.encode(ohlcv)

# 3. Predict price
predictor = PricePredictor()
prediction = predictor.predict(embedding)
print(f"Predicted: {prediction['mean']:.5f} ± {prediction['std']:.5f}")

# 4. Multi-agent voting
pattern = PatternAgent()
risk = RiskAgent()
orchestrator = MultiAgentOrchestrator(agents=[pattern, risk])

market_state = {'ohlc': ohlcv, 'operator_scores': {}}
trajectories = [{'id': 'traj_0', 'energy': 0.5, 'action': 0.1}]

votes = orchestrator.collect_votes(trajectories, market_state)
decision = orchestrator.aggregate_votes(votes)
print(f"Selected trajectory: {decision.selected_trajectory}")

# 5. Scheduler authorization
scheduler = Scheduler()
from trading.kernel.scheduler import CollapseDecision
collapse, token = scheduler.authorize_collapse(
    proposal={},
    projected_trajectories=trajectories,
    delta_s=0.3,
    constraints_passed=True,
    reconciliation_clear=True
)
print(f"Trade authorized: {collapse == CollapseDecision.AUTHORIZED}")
```

## 📚 Phase-by-Phase Guide

### Phase 1: Memory System (Vector DB)

**Purpose:** Store and retrieve market pattern embeddings for similarity search.

```python
from trading.memory import PatternVectorStore, get_embedder

# Store a pattern
store = PatternVectorStore()
embedding = get_embedder().encode(ohlcv)

store.store_pattern(
    embedding=embedding,
    symbol='EURUSD',
    metadata={'timeframe': '1h', 'outcome': 'win'},
    outcome=0.02  # PnL
)

# Find similar patterns
similar = store.find_similar_patterns(embedding, symbol='EURUSD', n_results=3)
```

**Components:**
- `MarketEmbedder`: OHLCV → 128-dim embedding
- `PatternVectorStore`: ChromaDB-backed pattern storage
- `MemoryAugmentedGenerator`: RAG-style trajectory generation

### Phase 2: Neural Price Predictor

**Purpose:** Predict price movements with uncertainty quantification.

```python
from trading.models import PricePredictor, train_synthetic

# Train on synthetic data
train_synthetic(n_samples=1000, epochs=10)

# Predict
predictor = PricePredictor()
embedding = get_embedder().encode(ohlcv)
prediction = predictor.predict(embedding)

print(f"Mean: {prediction['mean']:.5f}")
print(f"Std: {prediction['std']:.5f}")  # Uncertainty
print(f"Trend: {prediction['trend']:.2f}")
```

**Components:**
- `PricePredictor`: Transformer-based forecaster
- `train.py`: Training pipeline
- `InferenceCache`: Cached predictions for performance

### Phase 3: RL Agent (PPO)

**Purpose:** Learn optimal trajectory selection via reinforcement learning.

```python
from trading.rl import PPOSchedulerAgent, TradingEnvironment

# Create agent
agent = PPOSchedulerAgent(state_dim=166, action_dim=5)

# Build state
env = TradingEnvironment()
state = env.reset(embedding, trajectories, operator_scores)

# Select action
action, log_prob, value = agent.select_action(state)
selected_trajectory = trajectories[action]

# After trade, update agent
agent.store_transition(state, action, reward, log_prob, value, done=True)
metrics = agent.update()
```

**Components:**
- `PPOSchedulerAgent`: Proximal Policy Optimization
- `TradingEnvironment`: Gym-like trading environment
- `ActorCritic`: Policy network with shared features

### Phase 4: Multi-Agent System

**Purpose:** Collective intelligence through specialized agent voting.

```python
from trading.agents import (
    PatternAgent, RiskAgent, TimingAgent, StrategyAgent,
    MultiAgentOrchestrator, MetaAgent
)

# Create specialized agents
agents = [
    PatternAgent(weight=1.0),      # Pattern recognition
    RiskAgent(weight=1.0),          # Risk management
    TimingAgent(weight=1.0),        # Execution timing
    StrategyAgent(weight=1.2),      # LLM strategy
]

meta = MetaAgent()  # Performance monitoring

# Orchestrate voting
orchestrator = MultiAgentOrchestrator(
    agents=agents,
    meta_agent=meta,
    default_strategy='weighted'
)

votes = orchestrator.collect_votes(trajectories, market_state)
decision = orchestrator.aggregate_votes(votes)

print(f"Consensus: {decision.consensus_score:.2f}")
print(f"Selected: {decision.selected_trajectory}")

# Report outcome for learning
orchestrator.report_trade_outcome(pnl=0.02, selected_trajectory=1, decision=decision)
```

**Agents:**
- `PatternAgent`: Detects ICT/SMC patterns (FVG, OB, sweeps)
- `RiskAgent`: Kelly sizing, VaR, drawdown management
- `TimingAgent`: Spread analysis, session quality
- `MetaAgent`: Dynamic weight adjustment
- `StrategyAgent`: Natural language strategy generation

### Phase 5: LLM Strategy Generator

**Purpose:** Natural language strategy input with reasoning.

```python
from trading.agents import StrategyAgent

agent = StrategyAgent(llm_provider="mock")  # or "openai" if API key set

# Parse natural language
intent = agent.parse_strategy_input(
    "Buy EURUSD at bullish order block targeting 1.09 with 1% risk"
)

# Generate strategy
proposal = agent.generate_strategy(market_state, intent)

print(f"Entry: {proposal.parameters['entry_price']}")
print(f"Stop: {proposal.parameters['stop_loss']}")
print(f"Rationale: {proposal.reasoning}")
```

**Features:**
- Natural language parsing
- OpenAI/Claude/local model support
- Mock fallback when LLM unavailable
- ICT/SMC-aware prompts

## 🧪 Testing

### Run All Tests

```bash
# Unit tests
python -m pytest tests/ -v

# Integration tests
python tests/integration/test_full_pipeline.py

# Multi-agent tests
python test_multi_agent.py

# RL tests
python test_rl_integration.py

# Strategy agent tests
python test_strategy_agent.py
```

### Test Coverage

| Component | Status | Tests |
|-----------|--------|-------|
| Memory | ✅ | Phase 1 integration |
| NN Predictor | ✅ | Phase 2 integration |
| RL Agent | ✅ | 4/4 passing |
| Multi-Agent | ✅ | 5/5 passing |
| LLM Strategy | ✅ | 5/5 passing |
| **Full Pipeline** | ✅ | Integration suite |

## ⚙️ Configuration

### Environment Variables

```bash
# LLM Configuration
export OPENAI_API_KEY="your-key-here"
export ANTHROPIC_API_KEY="your-key-here"

# Vector DB
export CHROMA_PERSIST_DIR="~/.apexquantumict/vector_db"

# Model Paths
export NN_MODEL_PATH="./models/price_predictor.pt"
export RL_MODEL_PATH="./models/ppo_agent.pt"

# Trading Parameters
export MAX_RISK_PER_TRADE="0.02"
export DEFAULT_TIMEFRAME="1h"
```

### Config File

```yaml
# config/system.yaml
memory:
  embedding_dim: 128
  ohlcv_length: 100
  persist_path: "~/.apexquantumict/vector_db"

nn_predictor:
  model_type: "transformer"
  d_model: 128
  nhead: 4
  num_layers: 3

rl_agent:
  algorithm: "ppo"
  lr: 3e-4
  gamma: 0.99
  clip_epsilon: 0.2

agents:
  consensus_threshold: 0.6
  refusal_threshold: 0.5
  weight_update_frequency: 100

llm:
  provider: "auto"  # auto, openai, anthropic, mock
  model: "gpt-4"
  temperature: 0.2
```

## 🎭 Shadow Trading

Run the system in paper trading mode for validation:

```python
from trading.shadow import PaperBroker, ShadowModeRunner

# Initialize paper broker
broker = PaperBroker(
    initial_balance=10000.0,
    slippage_model="realistic",
    commission=0.0001
)

# Run shadow mode
runner = ShadowModeRunner(broker=broker)
for market_tick in data_stream:
    decision = runner.run_decision_cycle(market_tick)
    if decision.should_trade:
        result = broker.execute(decision.order)
        print(f"Paper trade: PnL={result.pnl:.4f}")

# Get performance report
metrics = broker.get_performance_metrics()
print(f"Win rate: {metrics['win_rate']:.2%}")
print(f"Sharpe: {metrics['sharpe_ratio']:.2f}")
```

## 📊 Performance

### Latency Targets

| Component | Target | Typical |
|-----------|--------|---------|
| Embedding | 5ms | 10ms |
| NN Prediction | 10ms | 20ms |
| Agent Voting | 50ms | 100ms |
| RL Action | 5ms | 10ms |
| **Total Decision** | **100ms** | **200ms** |

### Optimization

```python
# Enable optimizations
from trading.config import enable_optimizations

enable_optimizations({
    'cache_embeddings': True,
    'batch_predictions': True,
    'parallel_agents': True,
    'quantize_models': True
})
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                            │
│              (Natural Language / API / Dashboard)                │
└─────────────────────────┬───────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                    STRATEGY AGENT (Phase 5)                      │
│              LLM Strategy Generation & Validation                │
└─────────────────────────┬───────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                   MULTI-AGENT SYSTEM (Phase 4)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Pattern  │ │  Risk    │ │  Timing  │ │  Meta    │           │
│  │  Agent   │ │  Agent   │ │  Agent   │ │  Agent   │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       └─────────────┴─────────────┴──────────┘                │
│                          ↓                                      │
│                    Orchestrator (Vote Aggregation)              │
└─────────────────────────┬───────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                      SCHEDULER KERNEL                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Entropy     │  │    RL Agent  │  │  Collapse    │         │
│  │    Gate      │  │  (Phase 3)   │  │ Authorization│         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────┬───────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                     PREDICTION LAYER                             │
│  ┌────────────────────────┐  ┌────────────────────────┐           │
│  │  Price Predictor       │  │  Market Embedder       │           │
│  │  (Phase 2)            │  │  (Phase 1)             │           │
│  │  Transformer          │  │  128-dim encoding     │           │
│  └────────────────────────┘  └────────────────────────┘           │
└─────────────────────────┬───────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                      DATA SOURCES                               │
│         (OHLCV / Order Book / Fundamental / Alternative)         │
└─────────────────────────────────────────────────────────────────┘
```

## 🛡️ Safety & Risk Management

### Built-in Safeguards

1. **Refusal-First Policy**: Default is non-execution
2. **Multi-Agent Consensus**: No trade if agents disagree
3. **Entropy Gate**: High uncertainty → No trade
4. **Risk Limits**: Kelly sizing, max drawdown, position limits
5. **Kill Switch**: Automatic deactivation on performance degradation

### Risk Configuration

```python
from trading.agents import RiskAgent

risk_agent = RiskAgent(
    max_risk_per_trade=0.02,    # 2% max
    max_drawdown=0.15,         # 15% max
    kelly_fraction=0.5         # Half-Kelly
)
```

## 📖 Documentation

- [Architecture Guide](docs/ARCHITECTURE.md) - System design details
- [API Reference](docs/API.md) - Complete API documentation
- [Tutorials](docs/TUTORIAL.md) - Step-by-step guides
- [Examples](docs/examples/) - Working code examples

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - See [LICENSE](LICENSE) file.

## 🙏 Acknowledgments

- **Quantum Physics**: Path integral formulation inspired by Feynman
- **ICT/SMC**: Trading concepts from Inner Circle Trader / Smart Money Concepts
- **RL**: PPO algorithm from Schulman et al.
- **Transformers**: Attention mechanism from Vaswani et al.

---

**Status**: All 5 phases complete and tested ✅  
**Version**: 1.0.0  
**Last Updated**: 2026-04-17
