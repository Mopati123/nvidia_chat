"""
Risk Agent - Risk Management Specialist

Specializes in:
- Position sizing (Kelly criterion)
- Drawdown risk assessment
- Portfolio exposure limits
- Volatility-based risk metrics

Can refuse trades if risk exceeds thresholds.
"""

import numpy as np
from typing import Dict, List, Optional
from .base_agent import BaseAgent, AgentVote
import logging

logger = logging.getLogger(__name__)


class RiskAgent(BaseAgent):
    """
    Risk management specialist.
    
    Evaluates trade risk and recommends position sizing.
    Can refuse trades if risk exceeds acceptable levels.
    """
    
    def __init__(self,
                 name: str = "RiskAgent",
                 weight: float = 1.0,
                 max_risk_per_trade: float = 0.02,  # 2% max risk
                 max_drawdown: float = 0.15,       # 15% max drawdown
                 kelly_fraction: float = 0.5):    # Half-Kelly for safety
        super().__init__(name=name, agent_type="risk", weight=weight)
        
        # Risk parameters
        self.max_risk_per_trade = max_risk_per_trade
        self.max_drawdown = max_drawdown
        self.kelly_fraction = kelly_fraction
        
        # Current portfolio state
        self.current_drawdown = 0.0
        self.daily_pnl = []
        self.open_positions = 0
        
        # Volatility tracking
        self.volatility_window = []
        self.volatility_window_size = 20
    
    def vote(self,
            trajectories: List[Dict],
            market_state: Dict,
            context: Optional[Dict] = None) -> AgentVote:
        """
        Vote based on risk assessment.
        
        Evaluates risk metrics and either:
        - Approves with recommended position size
        - Refuses if risk too high
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
        
        # Compute risk metrics
        risk_metrics = self._compute_risk_metrics(market_state, trajectories)
        
        # Check critical risk limits
        if risk_metrics['total_risk'] > self.max_risk_per_trade:
            return AgentVote(
                agent_name=self.name,
                agent_type=self.agent_type,
                refusal=True,
                refusal_reason=f"Risk {risk_metrics['total_risk']:.2%} exceeds max {self.max_risk_per_trade:.2%}",
                rationale=f"Trade too risky: {risk_metrics['total_risk']:.2%} > {self.max_risk_per_trade:.2%}",
                metadata=risk_metrics
            )
        
        if self.current_drawdown > self.max_drawdown:
            return AgentVote(
                agent_name=self.name,
                agent_type=self.agent_type,
                refusal=True,
                refusal_reason=f"Drawdown {self.current_drawdown:.2%} exceeds max {self.max_drawdown:.2%}",
                rationale=f"High drawdown: {self.current_drawdown:.2%}",
                metadata=risk_metrics
            )
        
        # Score trajectories by risk-adjusted metrics
        trajectory_scores = {}
        for i, traj in enumerate(trajectories):
            score = self._score_trajectory_risk(traj, risk_metrics)
            trajectory_scores[i] = score
        
        # Select lowest risk trajectory
        if trajectory_scores:
            best_idx = min(trajectory_scores, key=trajectory_scores.get)
            # Convert to preference (lower risk = higher preference)
            # Invert score so lower risk = higher score
            best_score = 1.0 - trajectory_scores[best_idx]
        else:
            best_idx = 0
            best_score = 0.5
        
        # Confidence based on risk clarity
        confidence = self._compute_risk_confidence(risk_metrics)
        
        # Build rationale
        rationale = self._build_rationale(risk_metrics, best_idx)
        
        vote = AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            confidence=confidence,
            preferred_trajectory=best_idx,
            trajectory_scores=trajectory_scores,
            rationale=rationale,
            refusal=False,
            metadata={
                **risk_metrics,
                'kelly_size': self._compute_kelly_size(risk_metrics),
                'recommended_position': self._compute_position_size(risk_metrics)
            }
        )
        
        self._last_vote = vote
        self._last_trajectories = trajectories
        
        return vote
    
    def check_refusal(self,
                     market_state: Dict,
                     context: Optional[Dict] = None) -> tuple[bool, Optional[str]]:
        """
        Check if we should refuse based on risk conditions.
        """
        # Check basic conditions
        should_refuse, reason = super().check_refusal(market_state, context)
        if should_refuse:
            return should_refuse, reason
        
        # Check volatility too high
        volatility = market_state.get('volatility', 0)
        if volatility > 0.05:  # 5% volatility threshold
            return True, f"Volatility too high: {volatility:.2%}"
        
        # Check too many open positions
        if self.open_positions >= 3:
            return True, f"Too many open positions: {self.open_positions}"
        
        return False, None
    
    def _compute_risk_metrics(self,
                            market_state: Dict,
                            trajectories: List[Dict]) -> Dict:
        """
        Compute comprehensive risk metrics.
        
        Returns dict of risk measures.
        """
        ohlc = market_state.get('ohlc', [])
        
        # Price-based risk
        if len(ohlc) >= 2:
            closes = [c['close'] for c in ohlc]
            returns = np.diff(closes) / closes[:-1]
            
            # Volatility (annualized)
            volatility = np.std(returns) * np.sqrt(252)
            
            # Value at Risk (95%)
            var_95 = np.percentile(returns, 5)
            
            # Expected Shortfall
            es = np.mean([r for r in returns if r < var_95]) if len(returns) > 0 else 0
        else:
            volatility = 0.01
            var_95 = -0.01
            es = -0.02
        
        # Trajectory-specific risk
        trajectory_risks = []
        for traj in trajectories:
            # Risk based on action magnitude (larger actions = more risk)
            action = abs(traj.get('action', 0))
            energy = abs(traj.get('energy', 0))
            
            # Risk score
            risk = (action * 0.5 + energy * 0.5) * volatility
            trajectory_risks.append(risk)
        
        avg_traj_risk = np.mean(trajectory_risks) if trajectory_risks else 0.01
        max_traj_risk = max(trajectory_risks) if trajectory_risks else 0.01
        
        # Portfolio risk
        portfolio_risk = self.current_drawdown * 0.5 + avg_traj_risk
        
        return {
            'volatility': volatility,
            'var_95': var_95,
            'expected_shortfall': es,
            'avg_trajectory_risk': avg_traj_risk,
            'max_trajectory_risk': max_traj_risk,
            'portfolio_risk': portfolio_risk,
            'current_drawdown': self.current_drawdown,
            'total_risk': portfolio_risk + avg_traj_risk
        }
    
    def _score_trajectory_risk(self,
                              trajectory: Dict,
                              risk_metrics: Dict) -> float:
        """
        Score trajectory by risk (lower = better).
        
        Returns risk score where lower is better.
        """
        # Base risk from volatility
        base_risk = risk_metrics['volatility']
        
        # Trajectory-specific risk
        action = abs(trajectory.get('action', 0))
        energy = abs(trajectory.get('energy', 0))
        
        # Higher action/energy = more risk
        traj_risk = (action + energy) * 0.1
        
        # Combine
        total_risk = base_risk + traj_risk
        
        return total_risk
    
    def _compute_kelly_size(self, risk_metrics: Dict) -> float:
        """
        Compute Kelly criterion position size.
        
        Returns fraction of capital to risk.
        """
        # Simplified Kelly: win_rate - (1 - win_rate) / win_loss_ratio
        # Using historical performance
        
        if self.performance.total_trades < 10:
            # Not enough history, use conservative default
            return 0.01  # 1% risk
        
        win_rate = self.performance.win_rate
        
        # Estimate win/loss ratio from recent trades
        if self.performance.winning_trades > 0:
            avg_win = self.performance.cumulative_pnl / self.performance.winning_trades
        else:
            avg_win = 0.01
        
        losing_trades = self.performance.total_trades - self.performance.winning_trades
        if losing_trades > 0:
            avg_loss = abs(self.performance.cumulative_pnl - 
                         (avg_win * self.performance.winning_trades)) / losing_trades
        else:
            avg_loss = 0.01
        
        if avg_loss == 0:
            return 0.01
        
        win_loss_ratio = avg_win / avg_loss
        
        # Kelly formula
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Apply fraction and bounds
        kelly = max(0, kelly) * self.kelly_fraction
        kelly = min(kelly, self.max_risk_per_trade)
        
        return kelly
    
    def _compute_position_size(self, risk_metrics: Dict) -> float:
        """
        Compute recommended position size.
        
        Combines Kelly criterion with risk limits.
        """
        kelly = self._compute_kelly_size(risk_metrics)
        
        # Scale down if high volatility
        vol_adj = 1.0
        if risk_metrics['volatility'] > 0.3:
            vol_adj = 0.5
        elif risk_metrics['volatility'] > 0.2:
            vol_adj = 0.75
        
        # Scale down if high drawdown
        dd_adj = 1.0
        if self.current_drawdown > 0.1:
            dd_adj = 0.5
        elif self.current_drawdown > 0.05:
            dd_adj = 0.75
        
        # Final position size
        position_size = kelly * vol_adj * dd_adj
        
        # Hard cap
        position_size = min(position_size, self.max_risk_per_trade)
        
        return position_size
    
    def _compute_risk_confidence(self, risk_metrics: Dict) -> float:
        """
        Compute confidence based on risk clarity.
        
        Higher confidence when risk is well-quantified and acceptable.
        """
        # Factors that increase confidence
        low_vol = 1.0 if risk_metrics['volatility'] < 0.2 else 0.7
        low_dd = 1.0 if self.current_drawdown < 0.05 else 0.7
        
        # Compute confidence
        confidence = (low_vol + low_dd) / 2.0
        
        return confidence
    
    def _build_rationale(self,
                        risk_metrics: Dict,
                        best_idx: int) -> str:
        """Build human-readable rationale"""
        kelly = self._compute_kelly_size(risk_metrics)
        position = self._compute_position_size(risk_metrics)
        
        return (
            f"Risk metrics: vol={risk_metrics['volatility']:.2%}, "
            f"VaR_95={risk_metrics['var_95']:.2%}, "
            f"drawdown={self.current_drawdown:.2%}. "
            f"Kelly={kelly:.2%}, Position={position:.2%}. "
            f"Lowest risk trajectory: {best_idx}."
        )
    
    def update_drawdown(self, pnl: float, portfolio_value: float):
        """
        Update drawdown tracking.
        
        Args:
            pnl: Realized PnL
            portfolio_value: Current portfolio value
        """
        # Simple drawdown calculation
        if pnl < 0:
            self.current_drawdown = abs(pnl) / portfolio_value if portfolio_value > 0 else 0
        else:
            # Reduce drawdown on wins
            self.current_drawdown = max(0, self.current_drawdown - (pnl / portfolio_value))
    
    def update_open_positions(self, delta: int):
        """Update open position count"""
        self.open_positions = max(0, self.open_positions + delta)
