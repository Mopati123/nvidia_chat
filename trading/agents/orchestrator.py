"""
Multi-Agent Orchestrator

Coordinates voting from multiple specialized agents and aggregates
results to produce a unified decision for the scheduler.

Aggregation Strategies:
1. Simple Majority - Most common vote wins
2. Weighted Average - Weight by agent performance
3. Consensus Threshold - Only proceed if agreement > threshold
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass
from .base_agent import BaseAgent, AgentVote
from .meta_agent import MetaAgent
import logging

logger = logging.getLogger(__name__)


@dataclass
class AggregatedDecision:
    """
    Result of aggregating multiple agent votes.
    
    Attributes:
        selected_trajectory: Index of selected trajectory
        confidence: Overall confidence in decision
        consensus_score: Degree of agreement among agents
        refusal_count: How many agents refused
        total_votes: Total number of agents that voted
        agent_votes: All individual votes
        metadata: Additional info about aggregation
    """
    selected_trajectory: int
    confidence: float
    consensus_score: float
    refusal_count: int
    total_votes: int
    agent_votes: List[AgentVote]
    metadata: Dict
    refusal: bool = False
    refusal_reason: Optional[str] = None


class MultiAgentOrchestrator:
    """
    Orchestrates voting from multiple agents and aggregates results.
    
    Usage:
        orchestrator = MultiAgentOrchestrator(agents=[pattern, risk, timing])
        decision = orchestrator.aggregate_votes(votes, strategy='weighted')
    """
    
    def __init__(self,
                 agents: List[BaseAgent],
                 meta_agent: Optional[MetaAgent] = None,
                 default_strategy: str = 'weighted',
                 consensus_threshold: float = 0.6,
                 refusal_threshold: float = 0.5):
        """
        Initialize orchestrator.
        
        Args:
            agents: List of voting agents (not meta-agent)
            meta_agent: Optional meta-agent for weight management
            default_strategy: Default aggregation strategy
            consensus_threshold: Minimum agreement for consensus
            refusal_threshold: If > this fraction refuse, refuse overall
        """
        self.agents = agents
        self.meta_agent = meta_agent
        self.default_strategy = default_strategy
        self.consensus_threshold = consensus_threshold
        self.refusal_threshold = refusal_threshold
        
        # Register agents with meta-agent if available
        if meta_agent:
            for agent in agents:
                meta_agent.register_agent(agent)
        
        logger.info(
            f"Orchestrator initialized with {len(agents)} agents, "
            f"strategy={default_strategy}"
        )
    
    def collect_votes(self,
                   trajectories: List[Dict],
                   market_state: Dict,
                   context: Optional[Dict] = None) -> List[AgentVote]:
        """
        Collect votes from all active agents.
        
        Args:
            trajectories: List of candidate trajectories
            market_state: Current market state
            context: Optional additional context
        
        Returns:
            List of AgentVote objects
        """
        votes = []
        
        for agent in self.agents:
            if not agent.active:
                continue
            
            try:
                vote = agent.vote(trajectories, market_state, context)
                votes.append(vote)
            except Exception as e:
                logger.error(f"Agent {agent.name} voting failed: {e}")
                # Add abstain vote
                votes.append(AgentVote(
                    agent_name=agent.name,
                    agent_type=agent.agent_type,
                    refusal=True,
                    refusal_reason=f"Error: {e}",
                    rationale="Abstained due to error"
                ))
        
        return votes
    
    def aggregate_votes(self,
                       votes: List[AgentVote],
                       strategy: Optional[str] = None,
                       n_trajectories: int = 5) -> AggregatedDecision:
        """
        Aggregate votes using specified strategy.
        
        Args:
            votes: List of agent votes
            strategy: Aggregation strategy ('majority', 'weighted', 'consensus')
            n_trajectories: Number of trajectories to consider
        
        Returns:
            AggregatedDecision with selected trajectory and metadata
        """
        strategy = strategy or self.default_strategy
        
        # Check for overall refusal
        refusal_votes = [v for v in votes if v.refusal]
        if len(refusal_votes) > len(votes) * self.refusal_threshold:
            return AggregatedDecision(
                selected_trajectory=0,
                confidence=0.0,
                consensus_score=0.0,
                refusal_count=len(refusal_votes),
                total_votes=len(votes),
                agent_votes=votes,
                metadata={'strategy': strategy},
                refusal=True,
                refusal_reason=f"{len(refusal_votes)}/{len(votes)} agents refused"
            )
        
        # Filter out refusals for aggregation
        valid_votes = [v for v in votes if not v.refusal]
        
        if not valid_votes:
            return AggregatedDecision(
                selected_trajectory=0,
                confidence=0.0,
                consensus_score=0.0,
                refusal_count=len(refusal_votes),
                total_votes=len(votes),
                agent_votes=votes,
                metadata={'strategy': strategy},
                refusal=True,
                refusal_reason="All agents refused"
            )
        
        # Aggregate based on strategy
        if strategy == 'majority':
            selected, confidence, consensus = self._majority_vote(valid_votes, n_trajectories)
        elif strategy == 'weighted':
            selected, confidence, consensus = self._weighted_vote(valid_votes, n_trajectories)
        elif strategy == 'consensus':
            selected, confidence, consensus = self._consensus_vote(valid_votes, n_trajectories)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        return AggregatedDecision(
            selected_trajectory=selected,
            confidence=confidence,
            consensus_score=consensus,
            refusal_count=len(refusal_votes),
            total_votes=len(votes),
            agent_votes=votes,
            metadata={
                'strategy': strategy,
                'valid_votes': len(valid_votes),
                'weights': self._get_agent_weights()
            }
        )
    
    def _majority_vote(self,
                      votes: List[AgentVote],
                      n_trajectories: int) -> Tuple[int, float, float]:
        """
        Simple majority voting.
        
        Most common preferred trajectory wins.
        """
        preferences = [v.preferred_trajectory for v in votes]
        counts = Counter(preferences)
        
        if not counts:
            return 0, 0.0, 0.0
        
        selected = counts.most_common(1)[0][0]
        count = counts.most_common(1)[0][1]
        
        # Confidence based on proportion
        confidence = count / len(votes)
        
        # Consensus = agreement level
        consensus = confidence
        
        return selected, confidence, consensus
    
    def _weighted_vote(self,
                     votes: List[AgentVote],
                     n_trajectories: int) -> Tuple[int, float, float]:
        """
        Weighted voting by agent performance weights.
        
        Aggregates trajectory scores weighted by agent weights.
        """
        # Get weights from meta-agent or default
        weights = self._get_agent_weights()
        
        # Aggregate weighted scores per trajectory
        trajectory_scores = defaultdict(float)
        total_weight = 0
        
        for vote in votes:
            weight = weights.get(vote.agent_name, 1.0) * vote.confidence
            total_weight += weight
            
            # Add weighted scores
            for traj_idx, score in vote.trajectory_scores.items():
                trajectory_scores[traj_idx] += score * weight
        
        if not trajectory_scores or total_weight == 0:
            return 0, 0.0, 0.0
        
        # Normalize scores
        for idx in trajectory_scores:
            trajectory_scores[idx] /= total_weight
        
        # Select best
        selected = max(trajectory_scores, key=trajectory_scores.get)
        best_score = trajectory_scores[selected]
        
        # Confidence based on score spread
        scores = list(trajectory_scores.values())
        spread = max(scores) - min(scores)
        confidence = min(1.0, spread * 2.0)
        
        # Consensus based on agreement on top choice
        top_agreement = sum(1 for v in votes if v.preferred_trajectory == selected) / len(votes)
        consensus = top_agreement
        
        return selected, confidence, consensus
    
    def _consensus_vote(self,
                       votes: List[AgentVote],
                       n_trajectories: int) -> Tuple[int, float, float]:
        """
        Consensus-threshold voting.
        
        Only proceeds if agreement exceeds threshold.
        """
        preferences = [v.preferred_trajectory for v in votes]
        counts = Counter(preferences)
        
        if not counts:
            return 0, 0.0, 0.0
        
        selected, count = counts.most_common(1)[0]
        agreement = count / len(votes)
        
        # If consensus below threshold, select but with low confidence
        if agreement < self.consensus_threshold:
            confidence = agreement  # Lower confidence
            consensus = agreement
        else:
            confidence = 1.0
            consensus = agreement
        
        return selected, confidence, consensus
    
    def _get_agent_weights(self) -> Dict[str, float]:
        """Get current weights for all agents"""
        if self.meta_agent:
            return self.meta_agent.get_all_weights()
        else:
            # Default: all equal
            return {agent.name: agent.weight for agent in self.agents}
    
    def update_agent_weights(self, agent_name: str, weight: float):
        """Manually update an agent's weight"""
        for agent in self.agents:
            if agent.name == agent_name:
                agent.set_weight(weight)
                break
        
        if self.meta_agent:
            self.meta_agent.current_weights[agent_name] = weight
    
    def report_trade_outcome(self,
                           pnl: float,
                           selected_trajectory: int,
                           decision: AggregatedDecision):
        """
        Report trade outcome for agent performance tracking.
        
        Args:
            pnl: Realized PnL
            selected_trajectory: Which trajectory was selected
            decision: The aggregated decision that led to trade
        """
        # Update individual agents
        for vote in decision.agent_votes:
            agent = self._get_agent_by_name(vote.agent_name)
            if agent:
                was_followed = (vote.preferred_trajectory == selected_trajectory)
                agent.update_performance(pnl, selected_trajectory, {'was_followed': was_followed})
                
                # Update meta-agent if available
                if self.meta_agent:
                    self.meta_agent.update_agent_performance(
                        vote.agent_name, vote, pnl, was_followed
                    )
        
        logger.debug(
            f"Trade outcome reported: pnl={pnl:.4f}, "
            f"selected_traj={selected_trajectory}, "
            f"agents_updated={len(decision.agent_votes)}"
        )
    
    def _get_agent_by_name(self, name: str) -> Optional[BaseAgent]:
        """Get agent by name"""
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None
    
    def get_agent_status_report(self) -> Dict:
        """Get status report for all agents"""
        report = {
            'total_agents': len(self.agents),
            'active_agents': sum(1 for a in self.agents if a.active),
            'agents': {}
        }
        
        for agent in self.agents:
            report['agents'][agent.name] = agent.get_status()
        
        if self.meta_agent:
            report['meta_agent'] = self.meta_agent.get_system_report()
        
        return report
