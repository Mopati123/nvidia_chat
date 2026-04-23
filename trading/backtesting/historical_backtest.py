"""
Historical Backtest Runner — ApexQuantumICT

Runs the full 20-stage pipeline over historical OHLCV data (paper mode)
and reports Sharpe ratio, max drawdown, win rate, and trade log.

Data source: Deriv API (get_ohlcv) or a local CSV with columns:
    timestamp, open, high, low, close, volume

Usage (CLI):
    python -m trading.backtesting.historical_backtest --symbol EURUSD --days 30

Usage (API):
    from trading.backtesting.historical_backtest import run_backtest
    results = run_backtest("EURUSD", days=30)
    print(results["sharpe"], results["max_drawdown"])
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Window size — pipeline needs at least this many bars to compute geometry
_MIN_WINDOW = 20


def run_backtest(
    symbol: str,
    days: int = 30,
    granularity: int = 3600,
    initial_balance: float = 10_000.0,
    ohlcv_data: Optional[List[Dict]] = None,
) -> Dict:
    """
    Run the 20-stage pipeline over historical OHLCV and collect trade stats.

    Args:
        symbol: Trading symbol, e.g. "EURUSD"
        days: Number of calendar days to backtest (used to fetch data if ohlcv_data is None)
        granularity: Candle size in seconds (3600 = 1h, 86400 = 1d)
        initial_balance: Starting paper balance in USD
        ohlcv_data: Pre-fetched list of OHLCV dicts (skips Deriv fetch if provided)

    Returns:
        Dict with keys: trades, sharpe, max_drawdown, win_rate, final_balance, trade_log
    """
    from trading.pipeline.orchestrator import PipelineOrchestrator

    # ------------------------------------------------------------------
    # Fetch historical data if not provided
    # ------------------------------------------------------------------
    if ohlcv_data is None:
        deriv_symbol = "frx" + symbol if not symbol.startswith("frx") else symbol
        count = days * (86400 // granularity)
        logger.info("Fetching %d bars of %s from Deriv...", count, deriv_symbol)
        try:
            from trading.brokers.deriv_broker import DerivBroker
            broker = DerivBroker()
            if not broker.connect():
                logger.error("Cannot connect to Deriv for backtest data")
                return _empty_result()
            ohlcv_data = broker.get_ohlcv(deriv_symbol, granularity=granularity, count=count)
            broker.disconnect()
            logger.info("Fetched %d bars", len(ohlcv_data))
        except Exception as exc:
            logger.error("Data fetch failed: %s", exc)
            return _empty_result()

    if len(ohlcv_data) < _MIN_WINDOW + 1:
        logger.error("Insufficient data: %d bars (need > %d)", len(ohlcv_data), _MIN_WINDOW)
        return _empty_result()

    # ------------------------------------------------------------------
    # Normalise column names
    # ------------------------------------------------------------------
    def _norm(bar: Dict) -> Dict:
        out = {}
        for k, v in bar.items():
            key = k.lower().strip()
            if key == "timestamp":
                key = "time"
            out[key] = v
        return out

    bars = [_norm(b) for b in ohlcv_data]

    # ------------------------------------------------------------------
    # Initialise pipeline (paper mode)
    # ------------------------------------------------------------------
    orch = PipelineOrchestrator()
    orch._paper_mode = True

    trades: List[Dict] = []
    balance = initial_balance
    start_ts = time.time()

    logger.info("Running backtest on %d bars for %s...", len(bars), symbol)

    for i in range(_MIN_WINDOW, len(bars)):
        window = bars[i - _MIN_WINDOW: i]

        # Build synthetic OHLCV dict (lists, not individual values)
        ohlcv = {
            "open":   [b.get("open",  b.get("close", 1.0)) for b in window],
            "high":   [b.get("high",  b.get("close", 1.0)) for b in window],
            "low":    [b.get("low",   b.get("close", 1.0)) for b in window],
            "close":  [b.get("close", 1.0) for b in window],
            "volume": [b.get("volume", 0) for b in window],
            "time":   [b.get("time",  i) for b in window],
        }

        try:
            ctx = orch.execute(ohlcv, symbol=symbol, source="BACKTEST")
        except Exception as exc:
            logger.debug("Pipeline error at bar %d: %s", i, exc)
            continue

        if ctx.collapse_decision == "AUTHORIZED" and ctx.proposal:
            pnl = ctx.proposal.get("predicted_pnl", 0.0)
            balance += pnl
            trades.append({
                "bar": i,
                "direction": ctx.proposal.get("direction", "?"),
                "entry": ctx.proposal.get("entry", 0.0),
                "stop": ctx.proposal.get("stop", 0.0),
                "target": ctx.proposal.get("target", 0.0),
                "size": ctx.proposal.get("size", 0.0),
                "predicted_pnl": pnl,
                "balance": balance,
            })

    elapsed = time.time() - start_ts
    logger.info(
        "Backtest complete: %d bars, %d trades, %.1f bars/s",
        len(bars), len(trades), len(bars) / max(elapsed, 0.001)
    )

    return compute_stats(trades, initial_balance)


def compute_stats(trades: List[Dict], initial_balance: float = 10_000.0) -> Dict:
    """Compute Sharpe, max drawdown, win rate from a list of trade records."""
    if not trades:
        return _empty_result()

    pnls = np.array([t["predicted_pnl"] for t in trades], dtype=float)
    balances = np.array([t["balance"] for t in trades], dtype=float)

    # Sharpe (annualised, assuming hourly bars → 252*24 periods/year)
    mean_ret = pnls.mean()
    std_ret = pnls.std() + 1e-9
    sharpe = (mean_ret / std_ret) * np.sqrt(252 * 24)

    # Max drawdown
    peak = initial_balance
    max_dd = 0.0
    for b in balances:
        peak = max(peak, b)
        dd = (peak - b) / peak
        max_dd = max(max_dd, dd)

    win_rate = float((pnls > 0).sum()) / len(pnls)
    final_balance = float(balances[-1]) if len(balances) else initial_balance

    return {
        "trades": len(trades),
        "sharpe": round(float(sharpe), 3),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(win_rate, 3),
        "final_balance": round(final_balance, 2),
        "net_pnl": round(final_balance - initial_balance, 2),
        "trade_log": trades,
    }


def _empty_result() -> Dict:
    return {
        "trades": 0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "final_balance": 0.0,
        "net_pnl": 0.0,
        "trade_log": [],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(description="ApexQuantumICT Historical Backtest")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--granularity", type=int, default=3600,
        help="Candle granularity in seconds (default: 3600 = 1h)"
    )
    parser.add_argument("--balance", type=float, default=10_000.0)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    results = run_backtest(
        symbol=args.symbol,
        days=args.days,
        granularity=args.granularity,
        initial_balance=args.balance,
    )

    print("\n" + "=" * 50)
    print(f"  BACKTEST RESULTS — {args.symbol} ({args.days}d)")
    print("=" * 50)
    print(f"  Trades:       {results['trades']}")
    print(f"  Sharpe:       {results['sharpe']:.3f}  (target > 1.0)")
    print(f"  Max Drawdown: {results['max_drawdown']:.1%}  (target < 15%)")
    print(f"  Win Rate:     {results['win_rate']:.1%}")
    print(f"  Net PnL:      ${results['net_pnl']:+.2f}")
    print(f"  Final Bal:    ${results['final_balance']:.2f}")
    print("=" * 50)

    live_ready = results["sharpe"] > 1.0 and results["max_drawdown"] < 0.15
    print(f"\n  Live ready:   {'YES' if live_ready else 'NO — keep optimising'}")


if __name__ == "__main__":
    _cli()
