"""
PnL Tracker
Real-time profit/loss tracking across all brokers
Daily reset, auto-kill switch at loss limit
"""

import os
import json
import time
import logging
import numpy as np
from collections import deque
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from threading import Lock
from pathlib import Path

from trading.risk.risk_manager import get_risk_manager

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Record of a completed trade"""
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size: float
    realized_pnl: float
    entry_time: float
    exit_time: float
    broker: str
    metadata: Dict = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        return self.exit_time - self.entry_time
    
    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.realized_pnl / (self.entry_price * self.size)) * 100


class DailyPnLTracker:
    """
    Daily PnL tracking with persistence
    
    Features:
    - Real-time PnL across all brokers
    - Daily reset at midnight UTC
    - Auto-kill switch at loss limit
    - Trade history persistence
    - Performance metrics calculation
    """
    
    def __init__(
        self,
        data_dir: str = "trading_data/pnl",
        auto_kill: bool = True
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.auto_kill = auto_kill
        self.lock = Lock()
        
        # Current day state
        self.current_date = datetime.now(timezone.utc).date()
        self.daily_pnl = 0.0
        self.daily_trades: List[TradeRecord] = []
        self.peak_pnl = 0.0
        self.max_drawdown = 0.0
        
        # Running totals
        self.total_trades_all_time = 0
        self.total_pnl_all_time = 0.0
        
        # Rolling execution error histogram (last 100 trades)
        self.execution_errors: deque = deque(maxlen=100)

        # Risk manager reference
        self.risk_manager = get_risk_manager()

        # Load persisted state
        self._load_state()
        
        logger.info(f"PnLTracker initialized: date={self.current_date}, daily_pnl=${self.daily_pnl:.2f}")
    
    def _get_state_file(self) -> Path:
        """Get state file path for current date"""
        return self.data_dir / f"pnl_{self.current_date.isoformat()}.json"
    
    def _load_state(self):
        """Load persisted state for current date"""
        state_file = self._get_state_file()
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
                
                self.daily_pnl = data.get('daily_pnl', 0.0)
                self.peak_pnl = data.get('peak_pnl', 0.0)
                self.max_drawdown = data.get('max_drawdown', 0.0)
                
                # Load trade records
                trades_data = data.get('trades', [])
                self.daily_trades = [
                    TradeRecord(
                        trade_id=t['trade_id'],
                        symbol=t['symbol'],
                        direction=t['direction'],
                        entry_price=t['entry_price'],
                        exit_price=t['exit_price'],
                        size=t['size'],
                        realized_pnl=t['realized_pnl'],
                        entry_time=t['entry_time'],
                        exit_time=t['exit_time'],
                        broker=t['broker'],
                        metadata=t.get('metadata', {})
                    )
                    for t in trades_data
                ]
                
                logger.info(f"Loaded {len(self.daily_trades)} trades from {state_file}")
                
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Persist current state to disk"""
        state_file = self._get_state_file()
        
        data = {
            'date': self.current_date.isoformat(),
            'daily_pnl': self.daily_pnl,
            'peak_pnl': self.peak_pnl,
            'max_drawdown': self.max_drawdown,
            'trade_count': len(self.daily_trades),
            'trades': [
                {
                    'trade_id': t.trade_id,
                    'symbol': t.symbol,
                    'direction': t.direction,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'size': t.size,
                    'realized_pnl': t.realized_pnl,
                    'entry_time': t.entry_time,
                    'exit_time': t.exit_time,
                    'broker': t.broker,
                    'metadata': t.metadata
                }
                for t in self.daily_trades
            ],
            'saved_at': time.time()
        }
        
        try:
            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def record_execution_error(self, predicted_pnl: float, realized_pnl: float):
        """Record execution error ratio into the rolling histogram."""
        ratio = abs(predicted_pnl - realized_pnl) / max(abs(predicted_pnl), 1.0)
        self.execution_errors.append(ratio)

    def get_divergence_stats(self) -> Dict:
        """Return mean/std/p95 of the rolling execution error histogram."""
        if not self.execution_errors:
            return {'mean': 0.0, 'std': 0.0, 'p95': 0.0, 'count': 0}
        arr = np.array(self.execution_errors)
        return {
            'mean': float(arr.mean()),
            'std': float(arr.std()),
            'p95': float(np.percentile(arr, 95)),
            'count': len(arr)
        }

    def _check_daily_reset(self):
        """Check and perform daily reset if needed"""
        current_date = datetime.now(timezone.utc).date()
        
        if current_date != self.current_date:
            with self.lock:
                # Save yesterday's state
                self._save_state()
                
                # Archive summary
                self._archive_daily_summary()
                
                # Reset for new day
                logger.info(f"Daily reset: {self.current_date} -> {current_date}")
                self.current_date = current_date
                self.daily_pnl = 0.0
                self.daily_trades = []
                self.peak_pnl = 0.0
                self.max_drawdown = 0.0
                
                # Load any existing state for new day
                self._load_state()
    
    def _archive_daily_summary(self):
        """Archive summary of completed trading day"""
        if not self.daily_trades:
            return
        
        wins = [t for t in self.daily_trades if t.realized_pnl > 0]
        losses = [t for t in self.daily_trades if t.realized_pnl < 0]
        
        summary = {
            'date': self.current_date.isoformat(),
            'total_pnl': self.daily_pnl,
            'total_trades': len(self.daily_trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': len(wins) / len(self.daily_trades) if self.daily_trades else 0,
            'avg_win': sum(t.realized_pnl for t in wins) / len(wins) if wins else 0,
            'avg_loss': sum(t.realized_pnl for t in losses) / len(losses) if losses else 0,
            'max_drawdown': self.max_drawdown,
            'sharpe_approx': self._calculate_sharpe_approx(),
            'brokers_used': list(set(t.broker for t in self.daily_trades))
        }
        
        archive_file = self.data_dir / f"summary_{self.current_date.isoformat()}.json"
        with open(archive_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Daily summary archived: {summary}")
    
    def _calculate_sharpe_approx(self) -> float:
        """Calculate approximate Sharpe ratio from daily trades"""
        if len(self.daily_trades) < 2:
            return 0.0
        
        returns = [t.return_pct for t in self.daily_trades]
        avg_return = sum(returns) / len(returns)
        
        # Std dev
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5
        
        if std_dev == 0:
            return 0.0
        
        # Sharpe = (return - risk_free) / std_dev, assuming risk_free = 0
        return avg_return / std_dev
    
    def record_trade(self, trade: TradeRecord):
        """
        Record a completed trade
        
        Updates PnL, metrics, and checks kill switch
        """
        self._check_daily_reset()
        
        with self.lock:
            self.daily_trades.append(trade)
            self.daily_pnl += trade.realized_pnl
            self.total_trades_all_time += 1
            self.total_pnl_all_time += trade.realized_pnl
            
            # Update peak and drawdown
            if self.daily_pnl > self.peak_pnl:
                self.peak_pnl = self.daily_pnl
            
            current_dd = self.peak_pnl - self.daily_pnl
            if current_dd > self.max_drawdown:
                self.max_drawdown = current_dd
            
            # Save state
            self._save_state()
        
        logger.info(f"Trade recorded: {trade.trade_id} PnL=${trade.realized_pnl:.2f} "
                   f"Total=${self.daily_pnl:.2f}")
        
        # Check kill switch
        if self.auto_kill:
            self._check_kill_switch()
    
    def _check_kill_switch(self):
        """Check if daily loss limit breached and trigger kill switch"""
        daily_loss_limit = self.risk_manager.daily_loss_limit
        
        if self.daily_pnl <= -daily_loss_limit:
            logger.critical(f"DAILY LOSS LIMIT BREACHED: ${self.daily_pnl:.2f} / ${daily_loss_limit:.2f}")
            self.risk_manager.trigger_kill_switch("daily_loss_limit")
    
    def get_current_pnl(self, include_unrealized: bool = False) -> float:
        """Get current daily PnL"""
        self._check_daily_reset()
        
        if include_unrealized:
            # Get unrealized from risk manager positions
            unrealized = sum(
                p.unrealized_pnl
                for p in self.risk_manager.positions.values()
            )
            return self.daily_pnl + unrealized
        
        return self.daily_pnl
    
    def get_daily_stats(self) -> Dict:
        """Get comprehensive daily statistics"""
        self._check_daily_reset()
        
        with self.lock:
            if not self.daily_trades:
                return {
                    'date': self.current_date.isoformat(),
                    'daily_pnl': 0.0,
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'max_drawdown': 0.0,
                    'remaining_limit': self.risk_manager.daily_loss_limit
                }
            
            wins = [t for t in self.daily_trades if t.realized_pnl > 0]
            losses = [t for t in self.daily_trades if t.realized_pnl < 0]
            
            remaining = self.risk_manager.daily_loss_limit - abs(min(0, self.daily_pnl))
            
            return {
                'date': self.current_date.isoformat(),
                'daily_pnl': self.daily_pnl,
                'total_trades': len(self.daily_trades),
                'winning_trades': len(wins),
                'losing_trades': len(losses),
                'win_rate': len(wins) / len(self.daily_trades),
                'avg_win': sum(t.realized_pnl for t in wins) / len(wins) if wins else 0,
                'avg_loss': sum(t.realized_pnl for t in losses) / len(losses) if losses else 0,
                'max_drawdown': self.max_drawdown,
                'peak_pnl': self.peak_pnl,
                'sharpe_approx': self._calculate_sharpe_approx(),
                'remaining_limit': remaining,
                'limit_breached': self.daily_pnl <= -self.risk_manager.daily_loss_limit
            }
    
    def get_trade_history(self, limit: int = 100) -> List[TradeRecord]:
        """Get recent trade history"""
        self._check_daily_reset()
        
        with self.lock:
            return sorted(
                self.daily_trades,
                key=lambda t: t.exit_time,
                reverse=True
            )[:limit]
    
    def generate_daily_report(self) -> str:
        """Generate formatted daily trading report"""
        stats = self.get_daily_stats()
        
        report = f"""
╔══════════════════════════════════════════════════════════╗
║         DAILY PnL REPORT - {stats['date']}           ║
╠══════════════════════════════════════════════════════════╣
║  Realized PnL:      ${stats['daily_pnl']:+,.2f}                       ║
║  Total Trades:      {stats['total_trades']:>3}                              ║
║  Win Rate:          {stats['win_rate']:.1%}                           ║
║  Max Drawdown:      ${stats['max_drawdown']:,.2f}                       ║
╠══════════════════════════════════════════════════════════╣
║  Avg Win:           ${stats['avg_win']:+,.2f}                        ║
║  Avg Loss:          ${stats['avg_loss']:+,.2f}                        ║
╠══════════════════════════════════════════════════════════╣
║  Status: {'🚨 LIMIT BREACHED' if stats['limit_breached'] else '✅ Normal'}                        ║
╚══════════════════════════════════════════════════════════╝
"""
        return report


# Global instance
pnl_tracker: Optional[DailyPnLTracker] = None


def get_pnl_tracker(data_dir: str = "trading_data/pnl") -> DailyPnLTracker:
    """Get or create global PnL tracker"""
    global pnl_tracker
    if pnl_tracker is None:
        pnl_tracker = DailyPnLTracker(data_dir)
    return pnl_tracker


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create tracker
    tracker = get_pnl_tracker()
    
    # Simulate trades
    for i in range(5):
        trade = TradeRecord(
            trade_id=f"test_{i}",
            symbol='EURUSD',
            direction='buy',
            entry_price=1.0850,
            exit_price=1.0860 if i % 2 == 0 else 1.0840,
            size=0.1,
            realized_pnl=10.0 if i % 2 == 0 else -10.0,
            entry_time=time.time() - 3600,
            exit_time=time.time(),
            broker='deriv'
        )
        tracker.record_trade(trade)
    
    # Get report
    print(tracker.generate_daily_report())
    print(f"Stats: {tracker.get_daily_stats()}")
