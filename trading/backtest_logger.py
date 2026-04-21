"""
Backtest Logger
CSV/JSON export for analysis, trade journaling, performance metrics
"""

import os
import csv
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import time

logger = logging.getLogger(__name__)


@dataclass
class TradeLog:
    """Complete trade log entry"""
    trade_id: str
    timestamp: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size: float
    realized_pnl: float
    return_pct: float
    broker: str
    duration_seconds: float
    entry_signal: str
    exit_reason: str
    
    # TAEP data
    taep_authorized: bool
    taep_decision: str
    
    # Risk data
    risk_check_passed: bool
    max_drawdown_during_trade: float
    
    # Market conditions
    entry_rsi: float
    entry_ofi: float
    entry_volatility: float
    
    # Metadata
    tags: List[str]
    notes: str


class BacktestLogger:
    """
    Comprehensive backtest logging system
    
    Features:
    - CSV export for spreadsheet analysis
    - JSON export for programmatic analysis
    - Trade journaling with notes/tags
    - Performance metrics calculation
    - Daily summary reports
    """
    
    def __init__(
        self,
        data_dir: str = "trading_data/backtests",
        session_name: Optional[str] = None
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Session identification
        self.session_name = session_name or f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.session_dir = self.data_dir / self.session_name
        self.session_dir.mkdir(exist_ok=True)
        
        # File paths
        self.csv_file = self.session_dir / "trades.csv"
        self.json_file = self.session_dir / "trades.json"
        self.journal_file = self.session_dir / "journal.md"
        
        # In-memory storage
        self.trades: List[TradeLog] = []
        
        # Statistics
        self.session_start = time.time()
        self.metrics_calculated = False
        
        # Initialize CSV with headers if new
        self._init_csv()
        
        logger.info(f"BacktestLogger initialized: {self.session_name}")
    
    def _init_csv(self):
        """Initialize CSV file with headers"""
        if not self.csv_file.exists():
            headers = [
                'trade_id', 'timestamp', 'symbol', 'direction',
                'entry_price', 'exit_price', 'size', 'realized_pnl',
                'return_pct', 'broker', 'duration_seconds',
                'entry_signal', 'exit_reason', 'taep_authorized',
                'taep_decision', 'risk_check_passed', 'max_drawdown',
                'entry_rsi', 'entry_ofi', 'entry_volatility',
                'tags', 'notes'
            ]
            
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
    
    def log_trade(self, trade: TradeLog):
        """
        Log a completed trade
        
        Writes to CSV, JSON, and in-memory storage
        """
        self.trades.append(trade)
        
        # Append to CSV
        row = [
            trade.trade_id,
            trade.timestamp,
            trade.symbol,
            trade.direction,
            trade.entry_price,
            trade.exit_price,
            trade.size,
            trade.realized_pnl,
            trade.return_pct,
            trade.broker,
            trade.duration_seconds,
            trade.entry_signal,
            trade.exit_reason,
            trade.taep_authorized,
            trade.taep_decision,
            trade.risk_check_passed,
            trade.max_drawdown_during_trade,
            trade.entry_rsi,
            trade.entry_ofi,
            trade.entry_volatility,
            ','.join(trade.tags),
            trade.notes
        ]
        
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)
        
        # Append to JSON (line-delimited)
        with open(self.json_file, 'a') as f:
            f.write(json.dumps(asdict(trade)) + '\n')
        
        logger.info(f"Trade logged: {trade.trade_id} PnL=${trade.realized_pnl:.2f}")
    
    def add_journal_entry(self, title: str, content: str, tags: List[str] = None):
        """
        Add a manual journal entry
        
        For qualitative observations and trading notes
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        tag_str = ', '.join(tags) if tags else 'none'
        
        entry = f"""
## {title} - {timestamp}

**Tags:** {tag_str}

{content}

---
"""
        
        with open(self.journal_file, 'a') as f:
            f.write(entry + '\n')
        
        logger.info(f"Journal entry added: {title}")
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics
        
        Returns dict with all standard trading metrics
        """
        if not self.trades:
            return {'error': 'No trades to analyze'}
        
        # Basic counts
        total_trades = len(self.trades)
        wins = [t for t in self.trades if t.realized_pnl > 0]
        losses = [t for t in self.trades if t.realized_pnl < 0]
        break_even = [t for t in self.trades if t.realized_pnl == 0]
        
        win_count = len(wins)
        loss_count = len(losses)
        
        # PnL metrics
        total_pnl = sum(t.realized_pnl for t in self.trades)
        gross_profit = sum(t.realized_pnl for t in wins)
        gross_loss = sum(t.realized_pnl for t in losses)
        
        avg_pnl = total_pnl / total_trades
        avg_win = gross_profit / win_count if wins else 0
        avg_loss = gross_loss / loss_count if losses else 0
        
        # Win rate
        win_rate = win_count / total_trades if total_trades > 0 else 0
        
        # Profit factor
        profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')
        
        # Returns
        returns = [t.return_pct for t in self.trades]
        avg_return = sum(returns) / len(returns) if returns else 0
        
        # Risk metrics
        # Calculate running equity curve
        equity = [0.0]
        peak = 0.0
        max_dd = 0.0
        dd_start = 0.0
        
        for trade in self.trades:
            equity.append(equity[-1] + trade.realized_pnl)
            
            if equity[-1] > peak:
                peak = equity[-1]
            
            current_dd = peak - equity[-1]
            if current_dd > max_dd:
                max_dd = current_dd
        
        # Sharpe ratio (simplified)
        if len(returns) > 1:
            import statistics
            avg_ret = statistics.mean(returns)
            std_ret = statistics.stdev(returns) if len(returns) > 1 else 0
            sharpe = (avg_ret / std_ret) if std_ret > 0 else 0
        else:
            sharpe = 0
        
        # Expectancy
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        
        # By symbol
        by_symbol = {}
        for trade in self.trades:
            sym = trade.symbol
            if sym not in by_symbol:
                by_symbol[sym] = {'trades': 0, 'pnl': 0, 'wins': 0}
            by_symbol[sym]['trades'] += 1
            by_symbol[sym]['pnl'] += trade.realized_pnl
            if trade.realized_pnl > 0:
                by_symbol[sym]['wins'] += 1
        
        # By broker
        by_broker = {}
        for trade in self.trades:
            br = trade.broker
            if br not in by_broker:
                by_broker[br] = {'trades': 0, 'pnl': 0}
            by_broker[br]['trades'] += 1
            by_broker[br]['pnl'] += trade.realized_pnl
        
        metrics = {
            'summary': {
                'session_name': self.session_name,
                'session_duration_hours': (time.time() - self.session_start) / 3600,
                'total_trades': total_trades,
                'winning_trades': win_count,
                'losing_trades': loss_count,
                'break_even_trades': len(break_even),
                'win_rate': win_rate,
                'profit_factor': profit_factor
            },
            'pnl': {
                'total_pnl': total_pnl,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss,
                'avg_pnl_per_trade': avg_pnl,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'expectancy': expectancy
            },
            'returns': {
                'avg_return_pct': avg_return,
                'sharpe_ratio': sharpe
            },
            'risk': {
                'max_drawdown': max_dd,
                'final_equity': equity[-1] if equity else 0,
                'peak_equity': peak
            },
            'by_symbol': by_symbol,
            'by_broker': by_broker
        }
        
        self.metrics_calculated = True
        
        # Save metrics to file
        metrics_file = self.session_dir / "metrics.json"
        with open(metrics_file, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        return metrics
    
    def generate_report(self) -> str:
        """Generate formatted trading report"""
        metrics = self.calculate_metrics()
        
        if 'error' in metrics:
            return f"Error: {metrics['error']}"
        
        summary = metrics['summary']
        pnl = metrics['pnl']
        risk = metrics['risk']
        
        report = f"""
╔══════════════════════════════════════════════════════════════════╗
║           BACKTEST REPORT - {summary['session_name'][:30]:<30}    ║
╠══════════════════════════════════════════════════════════════════╣
║  Duration:        {summary['session_duration_hours']:.1f} hours                         ║
║  Total Trades:    {summary['total_trades']:<4} (W:{summary['winning_trades']} L:{summary['losing_trades']} BE:{summary['break_even_trades']})          ║
║  Win Rate:        {summary['win_rate']:.1%}                              ║
╠══════════════════════════════════════════════════════════════════╣
║  PnL:             ${pnl['total_pnl']:+,.2f}                        ║
║  Gross Profit:    ${pnl['gross_profit']:,.2f}                        ║
║  Gross Loss:      ${pnl['gross_loss']:,.2f}                        ║
║  Avg per Trade:   ${pnl['avg_pnl_per_trade']:+,.2f}                        ║
║  Profit Factor:   {summary['profit_factor']:.2f}                          ║
╠══════════════════════════════════════════════════════════════════╣
║  Max Drawdown:    ${risk['max_drawdown']:,.2f}                        ║
║  Peak Equity:     ${risk['peak_equity']:,.2f}                        ║
║  Final Equity:    ${risk['final_equity']:,.2f}                        ║
╚══════════════════════════════════════════════════════════════════╝
"""
        
        return report
    
    def export_for_analysis(self, filepath: str):
        """Export all data to single JSON file"""
        data = {
            'session': {
                'name': self.session_name,
                'start_time': datetime.fromtimestamp(
                    self.session_start, tz=timezone.utc
                ).isoformat(),
                'data_dir': str(self.session_dir)
            },
            'trades': [asdict(t) for t in self.trades],
            'metrics': self.calculate_metrics() if self.trades else {}
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Data exported to: {filepath}")
    
    def get_recent_trades(self, count: int = 10) -> List[TradeLog]:
        """Get recent trades"""
        return sorted(self.trades, key=lambda t: t.timestamp, reverse=True)[:count]
    
    def get_status(self) -> Dict:
        """Get logger status"""
        return {
            'session_name': self.session_name,
            'session_dir': str(self.session_dir),
            'trades_logged': len(self.trades),
            'csv_file': str(self.csv_file),
            'json_file': str(self.json_file),
            'journal_file': str(self.journal_file),
            'metrics_calculated': self.metrics_calculated
        }


# Global instance
backtest_logger: Optional[BacktestLogger] = None


def get_backtest_logger(
    session_name: Optional[str] = None,
    data_dir: str = "trading_data/backtests"
) -> BacktestLogger:
    """Get or create global backtest logger"""
    global backtest_logger
    if backtest_logger is None:
        backtest_logger = BacktestLogger(data_dir, session_name)
    return backtest_logger


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create logger
    logger_inst = get_backtest_logger(session_name="test_run")
    
    # Log some trades
    for i in range(10):
        trade = TradeLog(
            trade_id=f"trade_{i}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol='EURUSD',
            direction='buy',
            entry_price=1.0850,
            exit_price=1.0860 if i % 2 == 0 else 1.0840,
            size=0.1,
            realized_pnl=10.0 if i % 2 == 0 else -10.0,
            return_pct=0.1 if i % 2 == 0 else -0.1,
            broker='deriv',
            duration_seconds=300.0,
            entry_signal='RSI_OVERSOLD',
            exit_reason='TP_HIT' if i % 2 == 0 else 'SL_HIT',
            taep_authorized=True,
            taep_decision='ACCEPT',
            risk_check_passed=True,
            max_drawdown_during_trade=-5.0,
            entry_rsi=30.0,
            entry_ofi=100.0,
            entry_volatility=0.01,
            tags=['test'],
            notes='Sample trade'
        )
        logger_inst.log_trade(trade)
    
    # Generate report
    print(logger_inst.generate_report())
    
    # Add journal entry
    logger_inst.add_journal_entry(
        "Session Observations",
        "Market was volatile during London session.",
        tags=['observation', 'market']
    )
    
    print(f"Status: {logger_inst.get_status()}")
