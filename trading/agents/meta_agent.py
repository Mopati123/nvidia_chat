"""
Meta Agent - Performance Monitoring & Weight Adjustment

Specializes in:
- Tracking agent performance over time
- Computing dynamic voting weights
- Detecting agent degradation
- Triggering retraining when needed

The MetaAgent itself does not vote on trajectories but manages other agents.
"""

import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from .base_agent import BaseAgent
import logging

logger = logging.getLogger(__name__)


class MetaAgent(BaseAgent):
    """
    Performance monitoring and dynamic weight adjustment agent.
    
    Monitors all other agents and adjusts their voting weights
    based on recent performance.
    
    This agent does not vote on trajectories directly - it manages
    the performance and weights of other agents.
    """
    
    def __init__(self,
                 name: str = "MetaAgent",
                 weight_update_frequency: int = 100,  # Updates every N trades
                 lookback_window: int = 50,  # Trades to consider for weights
                 min_samples: int = 10,  # Minimum trades before weight adjustment
                 performance_threshold: float = 0.5):  # Accuracy threshold
        super().__init__(name=name, agent_type="meta", weight=0.0)  # No voting weight
        
        self.weight_update_frequency = weight_update_frequency
        self.lookback_window = lookback_window
        self.min_samples = min_samples
        self.performance_threshold = performance_threshold
        
        # Track trade count for update scheduling
        self.trade_count = 0
        self.last_update_trade = 0
        
        # Performance history per agent
        self.agent_performance_history: Dict[str, List[Dict]] = defaultdict(list)
        
        # Current weights (updated dynamically)
        self.current_weights: Dict[str, float] = {}
        
        # Agent status tracking
        self.agent_status: Dict[str, Dict] = {}
        
        logger.info(f"MetaAgent initialized: update_freq={weight_update_frequency}")
    
    def register_agent(self, agent: BaseAgent):
        """
        Register an agent for monitoring.
        
        Args:
            agent: Agent to monitor
        """
        self.current_weights[agent.name] = agent.weight
        self.agent_status[agent.name] = {
            'registered_at': datetime.now().isoformat(),
            'active': agent.active,
            'degradation_count': 0
        }
        logger.info(f"MetaAgent registered: {agent.name}")
    
    def update_agent_performance(self,
                                agent_name: str,
                                vote: 'AgentVote',
                                pnl: float,
                                was_followed: bool):
        """
        Record agent performance from a completed trade.
        
        Args:
            agent_name: Name of the agent
            vote: The vote cast by the agent
            pnl: Realized PnL
            was_followed: Whether agent's preference was selected
        """
        record = {
            'timestamp': datetime.now().isoformat(),
            'confidence': vote.confidence,
            'refusal': vote.refusal,
            'pnl': pnl,
            'was_followed': was_followed,
            'preferred_trajectory': vote.preferred_trajectory
        }
        
        self.agent_performance_history[agent_name].append(record)
        
        # Trim to lookback window
        if len(self.agent_performance_history[agent_name]) > self.lookback_window:
            self.agent_performance_history[agent_name] = \
                self.agent_performance_history[agent_name][-self.lookback_window:]
        
        self.trade_count += 1
        
        # Check if we should update weights
        if self.trade_count - self.last_update_trade >= self.weight_update_frequency:
            self.update_weights()
    
    def update_weights(self):
        """
        Update all agent weights based on recent performance.
        """
        logger.info("MetaAgent updating weights...")
        
        for agent_name, history in self.agent_performance_history.items():
            if len(history) < self.min_samples:
                continue  # Not enough data
            
            # Compute performance metrics
            metrics = self._compute_performance_metrics(history)
            
            # Compute new weight
            new_weight = self._compute_new_weight(agent_name, metrics)
            
            # Update
            old_weight = self.current_weights.get(agent_name, 1.0)
            self.current_weights[agent_name] = new_weight
            
            # Log change
            if abs(new_weight - old_weight) > 0.05:
                logger.info(
                    f"{agent_name} weight: {old_weight:.2f} -> {new_weight:.2f} "
                    f"(accuracy={metrics['accuracy']:.2%}, pnl={metrics['avg_pnl']:.4f})"
                )
            
            # Check for degradation
            if metrics['accuracy'] < self.performance_threshold and len(history) > self.min_samples:
                self.agent_status[agent_name]['degradation_count'] += 1
                logger.warning(
                    f"{agent_name} performance degraded: accuracy={metrics['accuracy']:.2%}"
                )
                
                # Consider deactivation after multiple degradations
                if self.agent_status[agent_name]['degradation_count'] >= 3:
                    logger.error(f"{agent_name} marked for deactivation due to consistent poor performance")
                    # In production, would deactivate here
            else:
                # Reset degradation count on good performance
                self.agent_status[agent_name]['degradation_count'] = max(
                    0, self.agent_status[agent_name]['degradation_count'] - 1
                )
        
        self.last_update_trade = self.trade_count
        
        # Normalize weights to sum to number of agents (average = 1.0)
        self._normalize_weights()
    
    def _compute_performance_metrics(self, history: List[Dict]) -> Dict:
        """
        Compute performance metrics from agent history.
        
        Returns:
            Dict with accuracy, win_rate, avg_pnl, etc.
        """
        if not history:
            return {'accuracy': 0.5, 'win_rate': 0.5, 'avg_pnl': 0, 'sharpe': 0}
        
        # Accuracy: when agent's preference was followed and led to win
        followed_votes = [h for h in history if h['was_followed']]
        if followed_votes:
            correct = sum(1 for h in followed_votes if h['pnl'] > 0)
            accuracy = correct / len(followed_votes)
        else:
            accuracy = 0.5
        
        # Win rate
        wins = sum(1 for h in history if h['pnl'] > 0)
        win_rate = wins / len(history)
        
        # Average PnL
        avg_pnl = np.mean([h['pnl'] for h in history])
        
        # Sharpe-like ratio
        pnls = [h['pnl'] for h in history]
        if len(pnls) > 1 and np.std(pnls) > 0:
            sharpe = np.mean(pnls) / np.std(pnls)
        else:
            sharpe = 0
        
        # Calibration: confidence vs accuracy
        high_conf_votes = [h for h in history if h['confidence'] > 0.7]
        if high_conf_votes:
            high_conf_accuracy = sum(1 for h in high_conf_votes if h['pnl'] > 0) / len(high_conf_votes)
        else:
            high_conf_accuracy = 0.5
        
        return {
            'accuracy': accuracy,
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'sharpe': sharpe,
            'total_trades': len(history),
            'calibration': high_conf_accuracy
        }
    
    def _compute_new_weight(self, agent_name: str, metrics: Dict) -> float:
        """
        Compute new weight based on performance metrics.
        
        Uses multi-factor weighting:
        - Accuracy: primary factor
        - Sharpe ratio: risk-adjusted performance
        - Calibration: confidence accuracy
        """
        # Base weight from accuracy
        accuracy_factor = metrics['accuracy']
        
        # Sharpe factor (normalized to 0-1 range)
        sharpe_factor = min(1.0, max(0.0, (metrics['sharpe'] + 2) / 4))
        
        # Calibration factor
        calibration_factor = metrics['calibration']
        
        # Combine factors
        performance_score = (
            accuracy_factor * 0.5 +
            sharpe_factor * 0.3 +
            calibration_factor * 0.2
        )
        
        # Map to weight range [0.5, 2.0]
        # 0.5 = underperforming, 2.0 = excellent
        weight = 0.5 + performance_score * 1.5
        
        # Penalty for degradation
        degradation_penalty = self.agent_status[agent_name].get('degradation_count', 0) * 0.1
        weight = max(0.2, weight - degradation_penalty)
        
        return round(weight, 2)
    
    def _normalize_weights(self):
        """Normalize weights so average is 1.0"""
        if not self.current_weights:
            return
        
        n_agents = len(self.current_weights)
        if n_agents == 0:
            return
        
        total = sum(self.current_weights.values())
        if total == 0:
            return
        
        # Scale so sum = n_agents (mean = 1.0)
        target_sum = n_agents
        scale = target_sum / total
        
        for name in self.current_weights:
            self.current_weights[name] *= scale
    
    def get_agent_weight(self, agent_name: str) -> float:
        """Get current weight for an agent"""
        return self.current_weights.get(agent_name, 1.0)
    
    def get_all_weights(self) -> Dict[str, float]:
        """Get all current weights"""
        return self.current_weights.copy()
    
    def get_agent_status(self, agent_name: str) -> Dict:
        """Get detailed status for an agent"""
        history = self.agent_performance_history.get(agent_name, [])
        metrics = self._compute_performance_metrics(history)
        
        # Add cumulative_pnl separately since it's not in the metrics dict
        total_pnl = sum(h.get('pnl', 0) for h in history)
        
        return {
            'name': agent_name,
            'current_weight': self.get_agent_weight(agent_name),
            'metrics': {
                **metrics,
                'cumulative_pnl': total_pnl
            },
            'status': self.agent_status.get(agent_name, {}),
            'history_length': len(history)
        }
    
    def get_system_report(self) -> Dict:
        """Get comprehensive report of all agents"""
        report = {
            'trade_count': self.trade_count,
            'last_update': self.last_update_trade,
            'agents': {}
        }
        
        for agent_name in self.current_weights:
            report['agents'][agent_name] = self.get_agent_status(agent_name)
        
        return report
    
    def should_retrain_agent(self, agent_name: str) -> bool:
        """
        Determine if an agent should be retrained.
        
        Returns True if:
        - Accuracy < threshold for extended period
        - Sharpe ratio negative and declining
        - Multiple degradation events
        """
        history = self.agent_performance_history.get(agent_name, [])
        if len(history) < self.min_samples:
            return False
        
        metrics = self._compute_performance_metrics(history)
        status = self.agent_status.get(agent_name, {})
        
        # Retrain if accuracy below threshold and significant history
        if metrics['accuracy'] < self.performance_threshold and len(history) > 20:
            return True
        
        # Retrain if multiple degradations
        if status.get('degradation_count', 0) >= 5:
            return True
        
        # Retrain if Sharpe declining
        if len(history) > 30:
            recent = history[-10:]
            older = history[-30:-10]
            
            recent_sharpe = np.mean([h['pnl'] for h in recent]) / (np.std([h['pnl'] for h in recent]) + 1e-8)
            older_sharpe = np.mean([h['pnl'] for h in older]) / (np.std([h['pnl'] for h in older]) + 1e-8)
            
            if recent_sharpe < older_sharpe * 0.5 and recent_sharpe < 0:
                return True
        
        return False
    
    def vote(self, trajectories, market_state, context=None):
        """
        MetaAgent does not vote on trajectories.
        This method exists for interface compatibility but should not be called.
        """
        raise NotImplementedError("MetaAgent does not vote on trajectories")
