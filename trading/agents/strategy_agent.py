"""
Strategy Agent - LLM-Powered Strategy Generation

Generates trading strategies from natural language input using LLM reasoning.
Integrates with the multi-agent system for validation and execution.

Key Capabilities:
- Natural language strategy parsing
- LLM-based strategy generation with ICT/SMC reasoning
- Multi-agent validation integration
- Strategy history and performance tracking
"""

import re
import logging
from typing import Dict, List, Optional, Any
from .base_agent import BaseAgent, AgentVote
from .llm_interface import (
    StrategyIntent, StrategyProposal,
    LLMInterfaceFactory, get_default_interface
)

logger = logging.getLogger(__name__)


class StrategyAgent(BaseAgent):
    """
    LLM-powered strategy generation agent.
    
    Parses natural language strategy descriptions and generates
    executable trading strategies with ICT/SMC reasoning.
    
    Example:
        >>> agent = StrategyAgent()
        >>> intent = agent.parse_strategy_input(
        ...     "Buy EURUSD at bullish order block targeting recent high"
        ... )
        >>> proposal = agent.generate_strategy(market_state, intent)
    """
    
    def __init__(
        self,
        name: str = "StrategyAgent",
        weight: float = 1.0,
        llm_provider: str = "auto",
        min_confidence: float = 0.5,
        strategy_history_size: int = 100
    ):
        super().__init__(
            name=name,
            agent_type="strategy",
            weight=weight,
            min_confidence=min_confidence
        )
        
        # Initialize LLM interface
        self.llm_interface = LLMInterfaceFactory.create_interface(llm_provider)
        logger.info(f"StrategyAgent using LLM: {type(self.llm_interface).__name__}")
        
        # Strategy history for learning
        self.strategy_history: List[Dict] = []
        self.max_history = strategy_history_size
        
        # Natural language patterns
        self._init_parsing_patterns()
    
    def _init_parsing_patterns(self):
        """Initialize regex patterns for NL parsing"""
        self.patterns = {
            'action': re.compile(
                r'\b(buy|sell|long|short|hold|wait)\b',
                re.IGNORECASE
            ),
            'asset': re.compile(
                r'\b(EURUSD|GBPUSD|USDJPY|BTCUSD|ETHUSD|XAUUSD|[A-Z]{6})\b'
            ),
            'timeframe': re.compile(
                r'\b(1m|5m|15m|30m|1h|4h|daily|weekly|monthly)\b',
                re.IGNORECASE
            ),
            'entry_trigger': re.compile(
                r'\b(at|when|if|on)\s+(?:the\s+)?(.+?)(?:\s+(?:targeting|with|and|or|$))',
                re.IGNORECASE
            ),
            'target': re.compile(
                r'\b(targeting|target|to|for)\s+(?:the\s+)?(.+?)(?:\s+(?:with|and|or|stop|$))',
                re.IGNORECASE
            ),
            'stop': re.compile(
                r'\b(stop|loss|below|above)\s+(?:at\s+)?(\d+\.?\d*)',
                re.IGNORECASE
            ),
            'risk': re.compile(
                r'(\d+)%\s+(?:risk|risking)',
                re.IGNORECASE
            ),
            'rr': re.compile(
                r'(\d+):(\d+)\s*(?:R:)?R',
                re.IGNORECASE
            )
        }
    
    def parse_strategy_input(self, nl_input: str) -> StrategyIntent:
        """
        Parse natural language strategy description.
        
        Args:
            nl_input: Natural language string like
                     "Buy EURUSD at bullish OB targeting 1.09 with 1% risk"
        
        Returns:
            StrategyIntent with extracted parameters
        """
        intent = StrategyIntent(raw_input=nl_input)
        
        # Extract action
        action_match = self.patterns['action'].search(nl_input)
        if action_match:
            action_word = action_match.group(1).lower()
            if action_word in ['buy', 'long']:
                intent.action = 'buy'
            elif action_word in ['sell', 'short']:
                intent.action = 'sell'
            else:
                intent.action = 'hold'
        
        # Extract asset
        asset_match = self.patterns['asset'].search(nl_input)
        if asset_match:
            intent.asset = asset_match.group(1).upper()
        
        # Extract timeframe
        tf_match = self.patterns['timeframe'].search(nl_input)
        if tf_match:
            intent.timeframe = tf_match.group(1).lower()
        
        # Extract entry conditions
        entry_match = self.patterns['entry_trigger'].search(nl_input)
        if entry_match:
            intent.entry_conditions.append(entry_match.group(2).strip())
        
        # Extract target/exit
        target_match = self.patterns['target'].search(nl_input)
        if target_match:
            intent.exit_conditions.append(f"Target: {target_match.group(2).strip()}")
        
        # Extract stop level
        stop_match = self.patterns['stop'].search(nl_input)
        if stop_match:
            intent.exit_conditions.append(f"Stop: {stop_match.group(2)}")
        
        # Extract risk
        risk_match = self.patterns['risk'].search(nl_input)
        if risk_match:
            intent.risk_constraints['max_loss'] = f"{risk_match.group(1)}%"
        
        # Extract R:R ratio
        rr_match = self.patterns['rr'].search(nl_input)
        if rr_match:
            r_val = int(rr_match.group(1))
            reward_val = int(rr_match.group(2))
            intent.risk_constraints['risk_reward'] = f"{r_val}:{reward_val}"
        
        # Add raw parse info to metadata
        intent.metadata['parse_confidence'] = self._estimate_parse_confidence(intent)
        
        logger.debug(f"Parsed intent: {intent.to_dict()}")
        
        return intent
    
    def _estimate_parse_confidence(self, intent: StrategyIntent) -> float:
        """Estimate confidence in parse quality"""
        score = 0.0
        checks = 0
        
        if intent.action != 'buy':  # Has explicit action
            score += 1
        checks += 1
        
        if intent.asset:
            score += 1
        checks += 1
        
        if intent.entry_conditions:
            score += 1
        checks += 1
        
        if intent.exit_conditions:
            score += 1
        checks += 1
        
        return score / checks if checks > 0 else 0.5
    
    def generate_strategy(
        self,
        market_state: Dict,
        intent: StrategyIntent
    ) -> StrategyProposal:
        """
        Generate executable strategy using LLM.
        
        Args:
            market_state: Current market state dict
            intent: Parsed strategy intent
        
        Returns:
            StrategyProposal with executable parameters
        """
        # Build market description
        market_desc = self._build_market_description(market_state)
        
        # Build context for LLM
        context = self._build_llm_context(market_state)
        
        # Generate using LLM
        try:
            proposal = self.llm_interface.generate_strategy(
                market_description=market_desc,
                strategy_intent=intent,
                context=context
            )
            
            # Store in history
            self._add_to_history(proposal)
            
            logger.info(
                f"Generated strategy: {proposal.intent.action} "
                f"@ {proposal.parameters.get('entry_price', 'N/A')} "
                f"(conf={proposal.confidence:.2f})"
            )
            
            return proposal
            
        except Exception as e:
            logger.error(f"Strategy generation failed: {e}")
            # Return fallback proposal
            return self._create_fallback_proposal(intent)
    
    def _build_market_description(self, market_state: Dict) -> str:
        """Build natural language market description"""
        parts = []
        
        # Current price
        ohlc = market_state.get('ohlc', [])
        if ohlc:
            latest = ohlc[-1]
            current_price = latest.get('close', 0)
            parts.append(f"Current price: {current_price:.5f}")
            
            # Recent range
            if len(ohlc) >= 20:
                recent = ohlc[-20:]
                high = max(c['high'] for c in recent)
                low = min(c['low'] for c in recent)
                parts.append(f"20-period range: {low:.5f} - {high:.5f}")
        
        # Trend
        trend = market_state.get('trend', 'neutral')
        parts.append(f"Trend: {trend}")
        
        # Volatility
        vol = market_state.get('volatility', 0)
        parts.append(f"Volatility: {vol:.2%}")
        
        return "\n".join(parts)
    
    def _build_llm_context(self, market_state: Dict) -> Dict:
        """Build context dict for LLM"""
        context = {}
        
        # Extract patterns if available
        if 'detected_patterns' in market_state:
            context['patterns'] = market_state['detected_patterns']
        
        # Metrics
        context['metrics'] = {
            'volatility': market_state.get('volatility', 0),
            'trend': market_state.get('trend', 'neutral'),
            'current_price': market_state.get('current_price', 0)
        }
        
        return context
    
    def _create_fallback_proposal(self, intent: StrategyIntent) -> StrategyProposal:
        """Create fallback proposal when LLM fails"""
        return StrategyProposal(
            intent=intent,
            parameters={
                'entry_price': None,
                'stop_loss': None,
                'take_profit': None,
                'position_size': 0.01,
                'entry_conditions': ['Manual discretion required'],
                'exit_conditions': ['Manual discretion required']
            },
            confidence=0.3,
            reasoning="Strategy generation failed. Manual review required.",
            operators_emphasized=[],
            trajectory_filters={'min_energy': 0.3},
            validation_required=True,
            metadata={'source': 'fallback', 'error': 'LLM generation failed'}
        )
    
    def _add_to_history(self, proposal: StrategyProposal):
        """Add proposal to history"""
        record = {
            'timestamp': proposal.intent.metadata.get('timestamp', ''),
            'proposal': proposal.to_dict(),
            'outcome': None  # Filled later
        }
        
        self.strategy_history.append(record)
        
        # Trim history
        if len(self.strategy_history) > self.max_history:
            self.strategy_history = self.strategy_history[-self.max_history:]
    
    def vote(self,
            trajectories: List[Dict],
            market_state: Dict,
            context: Optional[Dict] = None) -> AgentVote:
        """
        Vote on trajectory selection based on generated strategy.
        
        This is the integration point with the multi-agent system.
        """
        # Check for refusal conditions
        should_refuse, reason = self.check_refusal(market_state, context)
        if should_refuse:
            return AgentVote(
                agent_name=self.name,
                agent_type=self.agent_type,
                refusal=True,
                refusal_reason=reason,
                rationale=f"Refused: {reason}"
            )
        
        # Infer intent from market state if no explicit input
        if context and 'strategy_input' in context:
            intent = self.parse_strategy_input(context['strategy_input'])
        else:
            intent = self._infer_intent(market_state)
        
        # Generate strategy
        proposal = self.generate_strategy(market_state, intent)
        
        # Score trajectories based on strategy fit
        trajectory_scores = {}
        for i, traj in enumerate(trajectories):
            score = self._score_trajectory_strategy_fit(traj, proposal)
            trajectory_scores[i] = score
        
        # Determine preference
        if trajectory_scores:
            best_idx = max(trajectory_scores, key=trajectory_scores.get)
            best_score = trajectory_scores[best_idx]
        else:
            best_idx = 0
            best_score = 0.5
        
        # Confidence from strategy
        confidence = proposal.confidence
        
        # Build rationale
        rationale = self._build_strategy_rationale(proposal, best_idx)
        
        vote = AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            confidence=confidence,
            preferred_trajectory=best_idx,
            trajectory_scores=trajectory_scores,
            rationale=rationale,
            refusal=False,
            metadata={
                'proposal': proposal.to_dict(),
                'llm_used': type(self.llm_interface).__name__ != 'MockLLMInterface'
            }
        )
        
        self._last_vote = vote
        self._last_trajectories = trajectories
        
        return vote
    
    def _infer_intent(self, market_state: Dict) -> StrategyIntent:
        """Infer strategy intent from market state"""
        intent = StrategyIntent(action='buy')
        
        # Try to determine action from market conditions
        trend = market_state.get('trend', 'neutral')
        if trend == 'bullish':
            intent.action = 'buy'
        elif trend == 'bearish':
            intent.action = 'sell'
        
        # Extract asset if available
        intent.asset = market_state.get('symbol', 'Unknown')
        intent.timeframe = market_state.get('timeframe', '1h')
        
        intent.risk_constraints['max_loss'] = '1%'
        
        return intent
    
    def _score_trajectory_strategy_fit(
        self,
        trajectory: Dict,
        proposal: StrategyProposal
    ) -> float:
        """
        Score how well a trajectory fits the strategy.
        
        Higher score = better alignment with strategy.
        """
        score = 0.5  # Start neutral
        
        # Check operator alignment
        traj_ops = trajectory.get('operator_scores', {})
        preferred_ops = proposal.trajectory_filters.get('preferred_operators', [])
        
        for op in preferred_ops:
            if op in traj_ops:
                score += traj_ops[op] * 0.2
        
        # Check action direction
        action = trajectory.get('action', 0)
        if proposal.intent.action == 'buy' and action > 0:
            score += 0.1
        elif proposal.intent.action == 'sell' and action < 0:
            score += 0.1
        
        # Check energy level
        energy = abs(trajectory.get('energy', 0))
        min_energy = proposal.trajectory_filters.get('min_energy', 0.3)
        if energy >= min_energy:
            score += 0.1
        
        return min(1.0, score)
    
    def _build_strategy_rationale(self, proposal: StrategyProposal, best_idx: int) -> str:
        """Build rationale for strategy-based vote"""
        params = proposal.parameters
        
        return (
            f"Strategy: {proposal.intent.action.upper()} "
            f"@ {params.get('entry_price', 'N/A')} "
            f"→ {params.get('take_profit', ['N/A'])[0] if params.get('take_profit') else 'N/A'}. "
            f"Rationale: {proposal.reasoning[:60]}... "
            f"Selected trajectory {best_idx} as best fit."
        )
    
    def get_strategy_history(self, n: int = 10) -> List[Dict]:
        """Get recent strategy history"""
        return self.strategy_history[-n:]
    
    def update_strategy_outcome(self, proposal_id: str, pnl: float, success: bool):
        """Update strategy with outcome for learning"""
        for record in self.strategy_history:
            if record['proposal'].get('metadata', {}).get('id') == proposal_id:
                record['outcome'] = {
                    'pnl': pnl,
                    'success': success,
                    'timestamp': 'now'
                }
                break
    
    def get_status(self) -> Dict:
        """Get agent status with strategy info"""
        base_status = super().get_status()
        
        base_status['strategy_count'] = len(self.strategy_history)
        base_status['llm_available'] = self.llm_interface.is_available()
        base_status['llm_type'] = type(self.llm_interface).__name__
        
        return base_status
