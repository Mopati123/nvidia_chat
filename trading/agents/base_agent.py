"""
Base Agent Class for Multi-Agent Trading System

Abstract base class defining the interface for all specialized trading agents.
Each agent handles a distinct aspect of trade analysis and votes on trajectory selection.

First Principles:
- Each agent is a specialist in one domain
- Agents vote independently but are coordinated by orchestrator
- Agents can refuse to trade if conditions are unfavorable
- Performance is tracked for dynamic weight adjustment
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentVote:
    """
    Vote cast by an agent on trajectory selection.
    
    Attributes:
        agent_name: Unique identifier for the agent
        agent_type: Type/category of agent (pattern, risk, timing, etc.)
        confidence: How sure the agent is (0.0 to 1.0)
        preferred_trajectory: Index of the agent's preferred trajectory
        trajectory_scores: Dict mapping trajectory index to score
        rationale: Human-readable explanation for the vote
        refusal: If True, agent advises against trading
        refusal_reason: Why the agent refused (if applicable)
        metadata: Additional agent-specific data
        timestamp: When the vote was cast
    """
    agent_name: str
    agent_type: str
    confidence: float = 0.5
    preferred_trajectory: int = 0
    trajectory_scores: Dict[int, float] = field(default_factory=dict)
    rationale: str = ""
    refusal: bool = False
    refusal_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        """Convert vote to dictionary for logging/evidence"""
        return {
            'agent_name': self.agent_name,
            'agent_type': self.agent_type,
            'confidence': self.confidence,
            'preferred_trajectory': self.preferred_trajectory,
            'trajectory_scores': self.trajectory_scores,
            'rationale': self.rationale,
            'refusal': self.refusal,
            'refusal_reason': self.refusal_reason,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }


@dataclass
class AgentPerformance:
    """Performance metrics for an agent"""
    total_votes: int = 0
    correct_votes: int = 0  # When agent's preference led to winning trade
    total_trades: int = 0
    winning_trades: int = 0
    cumulative_pnl: float = 0.0
    avg_confidence: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def accuracy(self) -> float:
        """Voting accuracy (when agent was followed)"""
        if self.total_trades == 0:
            return 0.5
        return self.winning_trades / self.total_trades
    
    @property
    def win_rate(self) -> float:
        """Trade win rate"""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades
    
    def update(self, pnl: float, confidence: float):
        """Update performance with new trade result"""
        self.total_trades += 1
        self.cumulative_pnl += pnl
        
        if pnl > 0:
            self.winning_trades += 1
        
        # Update average confidence
        self.avg_confidence = (self.avg_confidence * (self.total_trades - 1) + confidence) / self.total_trades
        self.last_updated = datetime.now().isoformat()


class BaseAgent(ABC):
    """
    Abstract base class for all trading agents.
    
    All specialized agents must implement:
    - vote(): Cast vote on trajectory selection
    - update_performance(): Learn from trade outcomes
    
    Optional overrides:
    - preprocess_state(): Prepare market state for this agent
    - compute_confidence(): Override default confidence calculation
    """
    
    def __init__(self,
                 name: str,
                 agent_type: str,
                 weight: float = 1.0,
                 active: bool = True,
                 min_confidence: float = 0.3):
        self.name = name
        self.agent_type = agent_type
        self.weight = weight  # Voting weight in aggregation
        self.active = active
        self.min_confidence = min_confidence  # Minimum confidence to participate
        
        # Performance tracking
        self.performance = AgentPerformance()
        
        # Recent vote history for learning
        self._last_vote: Optional[AgentVote] = None
        self._last_trajectories: Optional[List[Dict]] = None
        
        logger.info(f"Initialized {agent_type} agent: {name} (weight={weight}, active={active})")
    
    @abstractmethod
    def vote(self,
            trajectories: List[Dict],
            market_state: Dict,
            context: Optional[Dict] = None) -> AgentVote:
        """
        Cast vote on trajectory selection.
        
        This is the core method each agent must implement.
        
        Args:
            trajectories: List of candidate trajectory dictionaries
            market_state: Current market state dict
            context: Optional additional context
        
        Returns:
            AgentVote with agent's recommendation
        """
        pass
    
    def update_performance(self, 
                         pnl: float,
                         selected_trajectory: int,
                         trade_context: Optional[Dict] = None):
        """
        Update agent performance with trade outcome.
        
        Called after trade closes to update learning.
        
        Args:
            pnl: Realized PnL from trade
            selected_trajectory: Which trajectory was selected (0-indexed)
            trade_context: Additional trade info
        """
        # Update performance metrics
        self.performance.update(pnl, self._last_vote.confidence if self._last_vote else 0.5)
        
        # Check if our preference was followed
        if self._last_vote and self._last_vote.preferred_trajectory == selected_trajectory:
            self.performance.correct_votes += 1
        
        self.performance.total_votes += 1
        
        # Log performance
        logger.debug(
            f"{self.name} performance update: "
            f"pnl={pnl:.4f}, accuracy={self.performance.accuracy:.2%}, "
            f"win_rate={self.performance.win_rate:.2%}"
        )
        
        # Clear last vote
        self._last_vote = None
        self._last_trajectories = None
    
    def preprocess_state(self, market_state: Dict) -> Dict:
        """
        Preprocess market state for this agent's specific needs.
        
        Override if agent needs specific data extraction.
        
        Args:
            market_state: Raw market state dict
        
        Returns:
            Preprocessed state dict
        """
        return market_state
    
    def compute_confidence(self, 
                         trajectory_scores: Dict[int, float],
                         market_state: Dict) -> float:
        """
        Compute confidence score from trajectory scores.
        
        Default: based on score spread (higher spread = higher confidence)
        Override for custom confidence logic.
        
        Args:
            trajectory_scores: Dict of trajectory index to score
            market_state: Current market state
        
        Returns:
            Confidence score in [0, 1]
        """
        if not trajectory_scores:
            return 0.0
        
        scores = list(trajectory_scores.values())
        if len(scores) < 2:
            return 0.5
        
        # Confidence based on score variance
        spread = max(scores) - min(scores)
        confidence = min(1.0, spread * 2.0)  # Scale: 0.5 spread = 1.0 confidence
        
        return max(0.0, min(1.0, confidence))
    
    def check_refusal(self, 
                     market_state: Dict,
                     context: Optional[Dict] = None) -> tuple[bool, Optional[str]]:
        """
        Check if agent should refuse to vote.
        
        Override for custom refusal logic.
        
        Args:
            market_state: Current market state
            context: Optional context
        
        Returns:
            (should_refuse, reason)
        """
        # Default: refuse if not active
        if not self.active:
            return True, "Agent inactive"
        
        # Refuse if insufficient data
        ohlc = market_state.get('ohlc', [])
        if len(ohlc) < 20:
            return True, "Insufficient data"
        
        return False, None
    
    def get_status(self) -> Dict:
        """Get agent status and performance summary"""
        return {
            'name': self.name,
            'type': self.agent_type,
            'active': self.active,
            'weight': self.weight,
            'performance': {
                'accuracy': self.performance.accuracy,
                'win_rate': self.performance.win_rate,
                'total_trades': self.performance.total_trades,
                'cumulative_pnl': self.performance.cumulative_pnl,
                'avg_confidence': self.performance.avg_confidence
            },
            'last_vote': self._last_vote.to_dict() if self._last_vote else None
        }
    
    def set_weight(self, weight: float):
        """Update agent voting weight"""
        old_weight = self.weight
        self.weight = max(0.0, weight)
        logger.debug(f"{self.name} weight updated: {old_weight:.2f} -> {self.weight:.2f}")
    
    def activate(self):
        """Activate agent"""
        self.active = True
        logger.info(f"{self.name} activated")
    
    def deactivate(self):
        """Deactivate agent"""
        self.active = False
        logger.info(f"{self.name} deactivated")


# Global agent registry
_agent_registry: Dict[str, BaseAgent] = {}


def register_agent(agent: BaseAgent):
    """Register agent in global registry"""
    global _agent_registry
    _agent_registry[agent.name] = agent
    logger.info(f"Registered agent: {agent.name}")


def get_agent(name: str) -> Optional[BaseAgent]:
    """Get agent from registry"""
    return _agent_registry.get(name)


def list_agents() -> List[str]:
    """List all registered agent names"""
    return list(_agent_registry.keys())


def reset_registry():
    """Clear agent registry (for testing)"""
    global _agent_registry
    _agent_registry = {}
