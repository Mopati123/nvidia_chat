"""
Multi-Agent Trading System

Specialized agents operating in parallel with weighted voting:
- PatternAgent: ICT/SMC pattern recognition
- RiskAgent: Risk management  
- TimingAgent: Execution timing optimization
- MetaAgent: Performance monitoring and weight adjustment
- StrategyAgent: LLM-powered strategy generation
- Orchestrator: Vote aggregation and decision coordination
"""

from .base_agent import BaseAgent, AgentVote, AgentPerformance, register_agent, get_agent, list_agents
from .pattern_agent import PatternAgent
from .risk_agent import RiskAgent
from .timing_agent import TimingAgent
from .meta_agent import MetaAgent
from .orchestrator import MultiAgentOrchestrator, AggregatedDecision
from .strategy_agent import StrategyAgent
from .llm_interface import (
    StrategyIntent,
    StrategyProposal,
    LLMInterfaceFactory,
    get_default_interface,
    MockLLMInterface,
    OpenAILLMInterface
)

__all__ = [
    # Base classes
    'BaseAgent',
    'AgentVote',
    'AgentPerformance',
    
    # Specialized agents
    'PatternAgent',
    'RiskAgent',
    'TimingAgent',
    'MetaAgent',
    'StrategyAgent',
    
    # Orchestration
    'MultiAgentOrchestrator',
    'AggregatedDecision',
    
    # LLM Interface
    'StrategyIntent',
    'StrategyProposal',
    'LLMInterfaceFactory',
    'get_default_interface',
    'MockLLMInterface',
    'OpenAILLMInterface',
    
    # Utilities
    'register_agent',
    'get_agent',
    'list_agents',
]
