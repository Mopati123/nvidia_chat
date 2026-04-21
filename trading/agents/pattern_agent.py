"""
Pattern Agent - ICT/SMC Pattern Recognition Specialist

Specializes in detecting and scoring ICT/SMC trading patterns:
- Fair Value Gaps (FVG)
- Order Blocks (OB)
- Liquidity Sweeps
- Breaker Blocks
- Mitigation Blocks

Votes based on pattern quality and historical success rates.
"""

import numpy as np
from typing import Dict, List, Optional
from .base_agent import BaseAgent, AgentVote
import logging

logger = logging.getLogger(__name__)


class PatternAgent(BaseAgent):
    """
    Pattern recognition specialist for ICT/SMC concepts.
    
    Scores trajectories based on detected pattern quality.
    """
    
    def __init__(self, 
                 name: str = "PatternAgent",
                 weight: float = 1.0,
                 pattern_weights: Optional[Dict[str, float]] = None):
        super().__init__(name=name, agent_type="pattern", weight=weight)
        
        # Pattern importance weights (tunable)
        self.pattern_weights = pattern_weights or {
            'fvg': 1.0,           # Fair Value Gap
            'order_block': 1.2,   # Order Block (high importance)
            'liquidity_sweep': 1.0,
            'breaker': 0.9,
            'mitigation': 0.8,
            'choch': 0.7,         # Change of Character
            'bos': 0.7            # Break of Structure
        }
        
        # Pattern detection thresholds
        self.thresholds = {
            'fvg_size': 0.001,      # Min FVG size as % of price
            'ob_strength': 0.6,     # Min OB strength score
            'sweep_depth': 0.005     # Min sweep depth as % of price
        }
    
    def vote(self,
            trajectories: List[Dict],
            market_state: Dict,
            context: Optional[Dict] = None) -> AgentVote:
        """
        Vote based on pattern analysis.
        
        Analyzes market state for patterns and scores trajectories
        based on pattern alignment.
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
        
        # Detect patterns in market state
        patterns = self._detect_patterns(market_state)
        
        # Score each trajectory based on pattern alignment
        trajectory_scores = {}
        for i, traj in enumerate(trajectories):
            score = self._score_trajectory(traj, patterns, market_state)
            trajectory_scores[i] = score
        
        # Determine preference
        if trajectory_scores:
            best_idx = max(trajectory_scores, key=trajectory_scores.get)
            best_score = trajectory_scores[best_idx]
        else:
            best_idx = 0
            best_score = 0.5
        
        # Compute confidence
        confidence = self.compute_confidence(trajectory_scores, market_state)
        
        # Build rationale
        rationale = self._build_rationale(patterns, best_idx, best_score)
        
        vote = AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            confidence=confidence,
            preferred_trajectory=best_idx,
            trajectory_scores=trajectory_scores,
            rationale=rationale,
            metadata={
                'detected_patterns': patterns,
                'pattern_count': len(patterns)
            }
        )
        
        # Store for performance tracking
        self._last_vote = vote
        self._last_trajectories = trajectories
        
        return vote
    
    def _detect_patterns(self, market_state: Dict) -> List[Dict]:
        """
        Detect ICT/SMC patterns in market data.
        
        Returns list of detected patterns with metadata.
        """
        patterns = []
        ohlc = market_state.get('ohlc', [])
        
        if len(ohlc) < 10:
            return patterns
        
        # Detect Fair Value Gaps
        fvg_patterns = self._detect_fvg(ohlc)
        patterns.extend(fvg_patterns)
        
        # Detect Order Blocks
        ob_patterns = self._detect_order_blocks(ohlc)
        patterns.extend(ob_patterns)
        
        # Detect Liquidity Sweeps
        sweep_patterns = self._detect_liquidity_sweeps(ohlc)
        patterns.extend(sweep_patterns)
        
        # Detect Breaker Blocks
        breaker_patterns = self._detect_breakers(ohlc)
        patterns.extend(breaker_patterns)
        
        return patterns
    
    def _detect_fvg(self, ohlc: List[Dict]) -> List[Dict]:
        """Detect Fair Value Gaps in price action"""
        patterns = []
        
        for i in range(2, len(ohlc)):
            prev = ohlc[i-2]
            curr = ohlc[i]
            
            # Bullish FVG: prev high < curr low
            if prev['high'] < curr['low']:
                gap_size = curr['low'] - prev['high']
                price = curr['close']
                gap_pct = gap_size / price
                
                if gap_pct >= self.thresholds['fvg_size']:
                    patterns.append({
                        'type': 'fvg',
                        'subtype': 'bullish',
                        'index': i,
                        'size': gap_pct,
                        'strength': min(1.0, gap_pct * 100),  # Normalize
                        'description': f"Bullish FVG at candle {i}, size={gap_pct:.4%}"
                    })
            
            # Bearish FVG: prev low > curr high
            elif prev['low'] > curr['high']:
                gap_size = prev['low'] - curr['high']
                price = curr['close']
                gap_pct = gap_size / price
                
                if gap_pct >= self.thresholds['fvg_size']:
                    patterns.append({
                        'type': 'fvg',
                        'subtype': 'bearish',
                        'index': i,
                        'size': gap_pct,
                        'strength': min(1.0, gap_pct * 100),
                        'description': f"Bearish FVG at candle {i}, size={gap_pct:.4%}"
                    })
        
        return patterns
    
    def _detect_order_blocks(self, ohlc: List[Dict]) -> List[Dict]:
        """Detect Order Blocks (supply/demand zones)"""
        patterns = []
        
        # Simplified OB detection: strong candle preceding a move
        for i in range(1, len(ohlc) - 1):
            prev = ohlc[i-1]
            curr = ohlc[i]
            next_c = ohlc[i+1]
            
            # Bullish OB: strong bearish candle followed by bullish move
            if (prev['close'] < prev['open'] and  # Bearish
                abs(prev['close'] - prev['open']) / prev['open'] > 0.005):  # Strong
                if next_c['close'] > curr['high']:  # Breakout
                    patterns.append({
                        'type': 'order_block',
                        'subtype': 'bullish',
                        'index': i,
                        'strength': 0.8,
                        'description': f"Bullish OB at candle {i}"
                    })
            
            # Bearish OB: strong bullish candle followed by bearish move
            elif (prev['close'] > prev['open'] and  # Bullish
                  abs(prev['close'] - prev['open']) / prev['open'] > 0.005):  # Strong
                if next_c['close'] < curr['low']:  # Breakdown
                    patterns.append({
                        'type': 'order_block',
                        'subtype': 'bearish',
                        'index': i,
                        'strength': 0.8,
                        'description': f"Bearish OB at candle {i}"
                    })
        
        return patterns
    
    def _detect_liquidity_sweeps(self, ohlc: List[Dict]) -> List[Dict]:
        """Detect Liquidity Sweeps (stop runs)"""
        patterns = []
        
        # Look for price spikes that reverse quickly
        for i in range(2, len(ohlc) - 1):
            prev = ohlc[i-1]
            curr = ohlc[i]
            next_c = ohlc[i+1]
            
            # Bullish sweep: spike below previous low then reverse up
            if curr['low'] < prev['low']:
                sweep_depth = (prev['low'] - curr['low']) / curr['close']
                if sweep_depth >= self.thresholds['sweep_depth']:
                    if next_c['close'] > curr['open']:  # Reversal
                        patterns.append({
                            'type': 'liquidity_sweep',
                            'subtype': 'bullish',
                            'index': i,
                            'depth': sweep_depth,
                            'strength': min(1.0, sweep_depth * 50),
                            'description': f"Bullish sweep at candle {i}, depth={sweep_depth:.4%}"
                        })
            
            # Bearish sweep: spike above previous high then reverse down
            elif curr['high'] > prev['high']:
                sweep_depth = (curr['high'] - prev['high']) / curr['close']
                if sweep_depth >= self.thresholds['sweep_depth']:
                    if next_c['close'] < curr['open']:  # Reversal
                        patterns.append({
                            'type': 'liquidity_sweep',
                            'subtype': 'bearish',
                            'index': i,
                            'depth': sweep_depth,
                            'strength': min(1.0, sweep_depth * 50),
                            'description': f"Bearish sweep at candle {i}, depth={sweep_depth:.4%}"
                        })
        
        return patterns
    
    def _detect_breakers(self, ohlc: List[Dict]) -> List[Dict]:
        """Detect Breaker Blocks"""
        patterns = []
        
        # Simplified: strong breakout then immediate reversal
        for i in range(2, len(ohlc) - 1):
            prev = ohlc[i-2]
            curr = ohlc[i-1]
            next_c = ohlc[i]
            
            # Bullish breaker: strong bullish move reversed
            if (curr['close'] > curr['open'] and
                curr['high'] > prev['high'] and  # Breakout
                next_c['close'] < curr['low']):  # Immediate reversal
                
                patterns.append({
                    'type': 'breaker',
                    'subtype': 'bullish',
                    'index': i-1,
                    'strength': 0.7,
                    'description': f"Bullish breaker at candle {i-1}"
                })
            
            # Bearish breaker: strong bearish move reversed
            elif (curr['close'] < curr['open'] and
                  curr['low'] < prev['low'] and  # Breakdown
                  next_c['close'] > curr['high']):  # Immediate reversal
                
                patterns.append({
                    'type': 'breaker',
                    'subtype': 'bearish',
                    'index': i-1,
                    'strength': 0.7,
                    'description': f"Bearish breaker at candle {i-1}"
                })
        
        return patterns
    
    def _score_trajectory(self,
                         trajectory: Dict,
                         patterns: List[Dict],
                         market_state: Dict) -> float:
        """
        Score trajectory based on pattern alignment.
        
        Higher score = better alignment with detected patterns.
        """
        if not patterns:
            return 0.5  # Neutral if no patterns
        
        score = 0.5  # Start neutral
        
        # Get trajectory direction
        traj_op_scores = trajectory.get('operator_scores', {})
        trend = traj_op_scores.get('kinetic', 0)  # Positive = bullish
        
        for pattern in patterns:
            pattern_type = pattern['type']
            subtype = pattern['subtype']
            strength = pattern['strength']
            weight = self.pattern_weights.get(pattern_type, 1.0)
            
            # Check alignment
            if trend > 0 and subtype == 'bullish':
                # Bullish trajectory + bullish pattern = good
                score += strength * weight * 0.2
            elif trend < 0 and subtype == 'bearish':
                # Bearish trajectory + bearish pattern = good
                score += strength * weight * 0.2
            else:
                # Misalignment = penalty
                score -= strength * weight * 0.1
        
        # Normalize to [0, 1]
        return max(0.0, min(1.0, score))
    
    def _build_rationale(self,
                        patterns: List[Dict],
                        best_idx: int,
                        best_score: float) -> str:
        """Build human-readable rationale for the vote"""
        if not patterns:
            return "No significant patterns detected, neutral vote"
        
        pattern_counts = {}
        for p in patterns:
            t = p['type']
            pattern_counts[t] = pattern_counts.get(t, 0) + 1
        
        pattern_str = ', '.join([f"{k}:{v}" for k, v in pattern_counts.items()])
        
        return (
            f"Detected {len(patterns)} patterns ({pattern_str}). "
            f"Preferred trajectory {best_idx} with score {best_score:.3f}. "
            f"Top patterns influence decision."
        )
