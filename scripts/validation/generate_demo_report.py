"""
Generate Paper Trading Demo Report
Analyze results and export performance metrics
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_latest_session():
    """Find the latest backtest session"""
    backtest_dir = Path("trading_data/backtests")
    
    if not backtest_dir.exists():
        return None
    
    # Find all session directories
    sessions = [d for d in backtest_dir.iterdir() if d.is_dir()]
    
    if not sessions:
        return None
    
    # Sort by modification time
    latest = max(sessions, key=lambda p: p.stat().st_mtime)
    return latest


def analyze_session(session_dir: Path):
    """Analyze a backtest session"""
    print(f"\nAnalyzing session: {session_dir.name}")
    print("="*60)
    
    # Check for files
    metrics_file = session_dir / "metrics.json"
    csv_file = session_dir / "trades.csv"
    json_file = session_dir / "trades.json"
    
    results = {
        'session_name': session_dir.name,
        'files_found': [],
        'metrics': None,
        'trade_count': 0
    }
    
    if metrics_file.exists():
        results['files_found'].append('metrics.json')
        try:
            with open(metrics_file, 'r') as f:
                results['metrics'] = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")
    
    if csv_file.exists():
        results['files_found'].append('trades.csv')
        # Count lines
        with open(csv_file, 'r') as f:
            lines = f.readlines()
            results['trade_count'] = max(0, len(lines) - 1)  # Exclude header
    
    if json_file.exists():
        results['files_found'].append('trades.json')
    
    return results


def print_performance_report(results: dict):
    """Print formatted performance report"""
    print("\n" + "="*60)
    print("PAPER TRADING DEMO - PERFORMANCE REPORT")
    print("="*60)
    
    session = results['session_name']
    print(f"Session: {session}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Files generated
    print("Files Generated:")
    for f in results['files_found']:
        print(f"  - {f}")
    print()
    
    # Metrics
    if results['metrics']:
        metrics = results['metrics']
        
        if 'summary' in metrics:
            summary = metrics['summary']
            print("Summary:")
            print(f"  Total Trades: {summary.get('total_trades', 0)}")
            print(f"  Winning Trades: {summary.get('winning_trades', 0)}")
            print(f"  Losing Trades: {summary.get('losing_trades', 0)}")
            print(f"  Win Rate: {summary.get('win_rate', 0):.1%}")
            print(f"  Profit Factor: {summary.get('profit_factor', 0):.2f}")
            print()
        
        if 'pnl' in metrics:
            pnl = metrics['pnl']
            print("Profit & Loss:")
            print(f"  Total PnL: ${pnl.get('total_pnl', 0):+.2f}")
            print(f"  Gross Profit: ${pnl.get('gross_profit', 0):.2f}")
            print(f"  Gross Loss: ${pnl.get('gross_loss', 0):.2f}")
            print(f"  Avg per Trade: ${pnl.get('avg_pnl_per_trade', 0):+.2f}")
            print()
        
        if 'risk' in metrics:
            risk = metrics['risk']
            print("Risk Metrics:")
            print(f"  Max Drawdown: ${risk.get('max_drawdown', 0):.2f}")
            print(f"  Peak Equity: ${risk.get('peak_equity', 0):.2f}")
            print(f"  Final Equity: ${risk.get('final_equity', 0):.2f}")
            print()
        
        if 'by_symbol' in metrics:
            print("Performance by Symbol:")
            for symbol, data in metrics['by_symbol'].items():
                print(f"  {symbol}: {data.get('trades', 0)} trades, ${data.get('pnl', 0):+.2f}")
            print()
        
        if 'by_broker' in metrics:
            print("Performance by Broker:")
            for broker, data in metrics['by_broker'].items():
                print(f"  {broker}: {data.get('trades', 0)} trades, ${data.get('pnl', 0):+.2f}")
            print()
    
    # Trade count from CSV
    if results['trade_count'] > 0:
        print(f"Total trades logged: {results['trade_count']}")
    
    print("="*60)


def export_summary_report(results: dict, output_file: str):
    """Export summary to file"""
    with open(output_file, 'w') as f:
        f.write("PAPER TRADING DEMO - SUMMARY REPORT\n")
        f.write("="*60 + "\n\n")
        f.write(f"Session: {results['session_name']}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        if results['metrics']:
            json.dump(results['metrics'], f, indent=2)
        
        f.write("\n\nFiles Generated:\n")
        for fname in results['files_found']:
            f.write(f"  - {fname}\n")
    
    logger.info(f"Summary report exported to: {output_file}")


def main():
    """Main report generation"""
    print("="*60)
    print("PAPER TRADING DEMO - RESULTS ANALYSIS")
    print("="*60)
    
    # Find latest session
    session_dir = find_latest_session()
    
    if not session_dir:
        print("\n[ERROR] No backtest sessions found!")
        print("Make sure paper trading demo was run first.")
        return 1
    
    # Analyze session
    results = analyze_session(session_dir)
    
    # Print report
    print_performance_report(results)
    
    # Export summary
    summary_file = session_dir / "demo_summary.txt"
    export_summary_report(results, str(summary_file))
    
    # Also export full data as JSON
    if results['metrics']:
        full_export = session_dir / "full_export.json"
        with open(full_export, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nFull export: {full_export}")
    
    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)
    print(f"\nReport files available in:")
    print(f"  {session_dir}")
    print("\nTo view CSV data in Excel:")
    print(f"  {session_dir / 'trades.csv'}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
