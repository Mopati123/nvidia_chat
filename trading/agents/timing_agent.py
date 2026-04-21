"""
Timing Agent - Execution Timing Specialist

Specializes in:
- Microstructure analysis (spread, depth, slippage)
- Optimal entry window detection
- Order book imbalance
- Latency-sensitive execution timing
"""

import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from .base_agent import BaseAgent, AgentVote
import logging

logger = logging.getLogger(__name__)


class TimingAgent(BaseAgent):
    """
    Execution timing specialist.
    
    Evaluates market microstructure and recommends optimal entry timing.
    Considers spread, depth, volatility clustering, and session dynamics.
    """
    
    def __init__(self,
                 name: str = "TimingAgent",
                 weight: float = 1.0,
                 max_spread_pct: float = 0.001,  # 10 bps max spread
                 min_liquidity_score: float = 0.6,
                 session_preference: Optional[str] = None):
        super().__init__(name=name, agent_type="timing", weight=weight)
        
        self.max_spread_pct = max_spread_pct
        self.min_liquidity_score = min_liquidity_score
        self.session_preference = session_preference  # 'london', 'ny', 'asia', or None
        
        # Timing state
        self.recent_spreads = []
        self.recent_volumes = []
        self.window_size = 10
        
        # Session times (simplified)
        self.sessions = {
            'asia': (0, 8),      # UTC 00:00 - 08:00
            'london': (8, 16),   # UTC 08:00 - 16:00
            'ny': (13, 21)       # UTC 13:00 - 21:00 (overlap with London)
        }
    
    def vote(self,
            trajectories: List[Dict],
            market_state: Dict,
            context: Optional[Dict] = None) -> AgentVote:
        """
        Vote based on execution timing analysis.
        
        Evaluates microstructure and scores timing quality.
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
        
        # Compute timing metrics
        timing_metrics = self._compute_timing_metrics(market_state)
        
        # Check if timing is unfavorable
        if timing_metrics['quality_score'] < 0.3:
            return AgentVote(
                agent_name=self.name,
                agent_type=self.agent_type,
                refusal=True,
                refusal_reason=f"Poor timing: quality={timing_metrics['quality_score']:.2f}",
                rationale=f"Timing unfavorable: spread={timing_metrics['spread']:.4%}, "
                         f"liquidity={timing_metrics['liquidity_score']:.2f}",
                metadata=timing_metrics
            )
        
        # Score trajectories by timing fit
        trajectory_scores = {}
        for i, traj in enumerate(trajectories):
            score = self._score_trajectory_timing(traj, timing_metrics)
            trajectory_scores[i] = score
        
        # Select best timing
        if trajectory_scores:
            best_idx = max(trajectory_scores, key=trajectory_scores.get)
            best_score = trajectory_scores[best_idx]
        else:
            best_idx = 0
            best_score = 0.5
        
        # Confidence based on timing clarity
        confidence = self._compute_timing_confidence(timing_metrics)
        
        # Build rationale
        rationale = self._build_rationale(timing_metrics, best_idx)
        
        vote = AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            confidence=confidence,
            preferred_trajectory=best_idx,
            trajectory_scores=trajectory_scores,
            rationale=rationale,
            refusal=False,
            metadata=timing_metrics
        )
        
        # Update tracking
        self._update_tracking(market_state)
        
        self._last_vote = vote
        self._last_trajectories = trajectories
        
        return vote
    
    def check_refusal(self,
                     market_state: Dict,
                     context: Optional[Dict] = None) -> tuple[bool, Optional[str]]:
        """Check if we should refuse based on timing conditions"""
        # Check basic conditions
        should_refuse, reason = super().check_refusal(market_state, context)
        if should_refuse:
            return should_refuse, reason
        
        # Check spread too wide
        ohlc = market_state.get('ohlc', [])
        if len(ohlc) > 0:
            latest = ohlc[-1]
            spread = (latest.get('high', 0) - latest.get('low', 0)) / latest.get('close', 1)
            if spread > self.max_spread_pct * 2:  # Double our normal max
                return True, f"Spread too wide: {spread:.4%}"
        
        # Check outside preferred session
        if self.session_preference:
            current_hour = datetime.utcnow().hour
            session_start, session_end = self.sessions.get(self.session_preference, (0, 24))
            if not (session_start <= current_hour < session_end):
                return True, f"Outside preferred session ({self.session_preference})"
        
        return False, None
    
    def _compute_timing_metrics(self, market_state: Dict) -> Dict:
        """
        Compute timing quality metrics.
        
        Returns dict of timing measures.
        """
        ohlc = market_state.get('ohlc', [])
        
        if len(ohlc) < 2:
            return {
                'spread': 0.01,
                'liquidity_score': 0.5,
                'volatility_trend': 0,
                'quality_score': 0.5,
                'optimal_delay': 0
            }
        
        # Current spread
        latest = ohlc[-1]
        spread = (latest.get('high', 0) - latest.get('low', 0)) / latest.get('close', 1)
        
        # Liquidity score (based on volume)
        volumes = [c.get('volume', 0) for c in ohlc[-10:]]
        avg_volume = np.mean(volumes) if volumes else 0
        volume_trend = volumes[-1] / avg_volume if avg_volume > 0 else 1.0
        liquidity_score = min(1.0, volume_trend * 0.7 + 0.3)
        
        # Volatility trend
        if len(ohlc) >= 10:
            recent = ohlc[-10:]
            recent_range = max(c['high'] for c in recent) - min(c['low'] for c in recent)
            recent_range_pct = recent_range / latest['close']
            
            # Lower volatility is better for timing
            volatility_score = max(0, 1.0 - recent_range_pct * 10)
        else:
            volatility_score = 0.5
        
        # Quality score (composite)
        spread_score = max(0, 1.0 - spread / self.max_spread_pct)
        quality_score = (spread_score * 0.4 + 
                        liquidity_score * 0.4 + 
                        volatility_score * 0.2)
        
        # Optimal delay (based on market conditions)
        if quality_score > 0.8:
            delay = 0  # Execute immediately
        elif quality_score > 0.5:
            delay = 1  # Wait 1 step
        else:
            delay = 2  # Wait 2 steps
        
        # Session quality
        current_hour = datetime.utcnow().hour
        session_quality = self._get_session_quality(current_hour)
        
        return {
            'spread': spread,
            'spread_score': spread_score,
            'liquidity_score': liquidity_score,
            'volume_trend': volume_trend,
            'volatility_score': volatility_score,
            'quality_score': quality_score,
            'optimal_delay': delay,
            'session_quality': session_quality,
            'current_session': self._get_current_session(current_hour)
        }
    
    def _score_trajectory_timing(self,
                                 trajectory: Dict,
                                 timing_metrics: Dict) -> float:
        """
        Score trajectory based on timing fit.
        
        Higher score = better timing alignment.
        """
        # Base score from quality
        score = timing_metrics['quality_score']
        
        # Adjust based on trajectory urgency
        # Fast trajectories need good timing more
        energy = abs(trajectory.get('energy', 0))
        if energy > 0.5:  # High energy trajectory
            # Needs excellent timing
            if timing_metrics['quality_score'] < 0.7:
                score *= 0.5  # Penalty
            else:
                score *= 1.2  # Bonus
        
        return min(1.0, score)
    
    def _compute_timing_confidence(self, timing_metrics: Dict) -> float:
        """
        Compute confidence based on timing clarity.
        
        Higher confidence when conditions are stable and favorable.
        """
        # High quality = high confidence
        quality_factor = timing_metrics['quality_score']
        
        # Stable volume = higher confidence
        stability_factor = 1.0 - abs(timing_metrics.get('volume_trend', 1) - 1) * 0.5
        
        # Session quality
        session_factor = timing_metrics.get('session_quality', 0.8)
        
        confidence = (quality_factor * 0.5 + 
                     stability_factor * 0.3 + 
                     session_factor * 0.2)
        
        return min(1.0, confidence)
    
    def _get_session_quality(self, current_hour: int) -> float:
        """
        Compute session quality based on time of day.
        
        Higher during major market sessions.
        """
        # London-NY overlap (13:00-16:00 UTC) is best
        if 13 <= current_hour < 16:
            return 1.0
        # London or NY alone
        elif 8 <= current_hour < 13 or 16 <= current_hour < 21:
            return 0.8
        # Asia session
        elif 0 <= current_hour < 8:
            return 0.6
        # Overnight
        else:
            return 0.4
    
    def _get_current_session(self, current_hour: int) -> str:
        """Get current market session name"""
        for session, (start, end) in self.sessions.items():
            if start <= current_hour < end:
                return session
        return "overnight"
    
    def _build_rationale(self,
                        timing_metrics: Dict,
                        best_idx: int) -> str:
        """Build human-readable rationale"""
        return (
            f"Timing analysis: spread={timing_metrics['spread']:.4%}, "
            f"liquidity={timing_metrics['liquidity_score']:.2f}, "
            f"quality={timing_metrics['quality_score']:.2f}, "
            f"session={timing_metrics['current_session']}, "
            f"delay={timing_metrics['optimal_delay']} steps. "
            f"Best trajectory: {best_idx}."
        )
    
    def _update_tracking(self, market_state: Dict):
        """Update internal tracking metrics"""
        ohlc = market_state.get('ohlc', [])
        if ohlc:
            latest = ohlc[-1]
            
            # Track spread
            spread = (latest.get('high', 0) - latest.get('low', 0)) / latest.get('close', 1)
            self.recent_spreads.append(spread)
            if len(self.recent_spreads) > self.window_size:
                self.recent_spreads.pop(0)
            
            # Track volume
            self.recent_volumes.append(latest.get('volume', 0))
            if len(self.recent_volumes) > self.window_size:
                self.recent_volumes.pop(0)
    
    def get_spread_trend(self) -> str:
        """Get trend of recent spreads"""
        if len(self.recent_spreads) < 3:
            return "insufficient_data"
        
        recent = np.mean(self.recent_spreads[-3:])
        older = np.mean(self.recent_spreads[:-3]) if len(self.recent_spreads) > 3 else recent
        
        if recent < older * 0.9:
            return "improving"
        elif recent > older * 1.1:
            return "worsening"
        else:
            return "stable"
