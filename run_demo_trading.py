"""
Live Demo Trading Launcher
Connects to Deriv demo + MT5 demo simultaneously.
Real ticks flow through the 20-stage pipeline.
Every trade result feeds the PPO reinforcement learning agent.

Usage:
    # Set credentials first (one-time):
    set DERIV_API_TOKEN=your_token
    set DERIV_APP_ID=your_app_id
    set MT5_ACCOUNT_ID=123456
    set MT5_PASSWORD=yourpassword
    set MT5_SERVER=Weltrade-Demo
    set APEX_CREDENTIAL_PASSWORD=any_local_password
    set DAILY_LOSS_LIMIT=200
    set MAX_RISK_PER_TRADE=0.01

    # Store credentials (one-time):
    python add_deriv_quick.py
    python add_mt5_quick.py

    # Run:
    python run_demo_trading.py [--symbol EURUSD] [--mode paper|deriv|mt5|both]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from threading import Thread, Lock
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("demo_trading")

# ---------------------------------------------------------------------------
# Tick → OHLCV accumulator
# ---------------------------------------------------------------------------

class TickAccumulator:
    """Accumulates raw ticks into OHLCV windows for the pipeline."""

    def __init__(self, window: int = 20, pipeline_interval: float = 5.0, min_ticks: int = 10):
        self._ticks: deque = deque(maxlen=window)
        self._last_run = 0.0
        self.pipeline_interval = pipeline_interval
        self.min_ticks = min_ticks
        self._lock = Lock()

    def add(self, price: float, ts: float) -> None:
        with self._lock:
            self._ticks.append((price, ts))

    def ready(self) -> bool:
        return (
            len(self._ticks) >= self.min_ticks
            and (time.time() - self._last_run) >= self.pipeline_interval
        )

    def to_ohlcv(self) -> Dict:
        with self._lock:
            prices = [t[0] for t in self._ticks]
            times  = [t[1] for t in self._ticks]
        n = len(prices)
        bar_size = max(1, n // 5)
        opens, highs, lows, closes, volumes, bar_times = [], [], [], [], [], []
        for i in range(0, n, bar_size):
            bar = prices[i : i + bar_size]
            opens.append(bar[0])
            highs.append(max(bar))
            lows.append(min(bar))
            closes.append(bar[-1])
            volumes.append(len(bar) * 100)
            bar_times.append(times[i])
        return {
            "open": opens, "high": highs, "low": lows,
            "close": closes, "volume": volumes, "time": bar_times,
        }

    def mark_run(self) -> None:
        self._last_run = time.time()


# ---------------------------------------------------------------------------
# Session stats
# ---------------------------------------------------------------------------

class SessionStats:
    def __init__(self):
        self.ticks_received = 0
        self.pipeline_runs = 0
        self.authorized = 0
        self.refused = 0
        self.ppo_updates = 0
        self.session_start = time.time()
        self._lock = Lock()

    def tick(self):
        with self._lock:
            self.ticks_received += 1

    def pipeline(self, decision: str):
        with self._lock:
            self.pipeline_runs += 1
            if decision == "AUTHORIZED":
                self.authorized += 1
            else:
                self.refused += 1

    def ppo_update(self):
        with self._lock:
            self.ppo_updates += 1

    def print_status(self, orch, ppo_agent, deriv_ok: bool, mt5_ok: bool):
        elapsed = time.time() - self.session_start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        try:
            rm_status = orch.risk_manager.get_status() if orch else {}
            pnl = rm_status.get("daily_pnl", 0.0)
            kill = rm_status.get("kill_switch", False)
        except Exception:
            pnl, kill = 0.0, False

        try:
            cb_state = orch.collapse_breaker.state.value if orch else "unknown"
        except Exception:
            cb_state = "unknown"

        try:
            divg = orch.divergence_history
            divg_mean = sum(divg) / len(divg) if divg else 0.0
        except Exception:
            divg_mean = 0.0

        print("\n" + "=" * 60)
        print(f"  DEMO TRADING STATUS  [{mins:02d}:{secs:02d} elapsed]")
        print("=" * 60)
        print(f"  Connections  Deriv: {'OK' if deriv_ok else 'OFF'}  |  MT5: {'OK' if mt5_ok else 'OFF'}")
        print(f"  Ticks recv:  {self.ticks_received:,}")
        print(f"  Pipeline:    {self.pipeline_runs} runs  ({self.authorized} auth / {self.refused} refused)")
        print(f"  Daily PnL:   ${pnl:+.2f}  {'[KILL SWITCH ON]' if kill else ''}")
        print(f"  Circuit:     {cb_state}")
        print(f"  PnL diverg:  {divg_mean:.1%} avg (last {len(divg) if orch else 0} trades)")
        print(f"  PPO updates: {self.ppo_updates}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# Core pipeline handler
# ---------------------------------------------------------------------------

def build_pipeline_handler(orch, ppo_hook, accumulator: TickAccumulator,
                            stats: SessionStats, symbol: str, mode: str):
    """Returns the function passed to AsyncTickLoop as pipeline_fn."""

    def handle_tick(source_tick: Tuple[str, Any]) -> None:
        source, tick = source_tick
        stats.tick()

        # Extract price from tick (Deriv dict or MT5 float)
        if isinstance(tick, dict):
            price = float(tick.get("bid") or tick.get("price") or tick.get("close", 0))
        elif isinstance(tick, (int, float)):
            price = float(tick)
        else:
            return

        if price <= 0:
            return

        accumulator.add(price, time.time())

        if not accumulator.ready():
            return

        accumulator.mark_run()
        raw_data = accumulator.to_ohlcv()

        try:
            ctx = orch.execute(raw_data, symbol=symbol, source=source.upper())
        except Exception as exc:
            logger.warning("Pipeline error: %s", exc)
            return

        decision = getattr(ctx, "collapse_decision", "REFUSED") or "REFUSED"
        stats.pipeline(decision)

        if decision == "AUTHORIZED" and ctx.proposal:
            p = ctx.proposal
            logger.info(
                "TRADE | %s %s @ %.5f | SL %.5f | TP %.5f | size %.2f | pPnL $%.1f",
                p.get("direction", "?").upper(), symbol,
                p.get("entry", 0), p.get("stop", 0),
                p.get("target", 0), p.get("size", 0),
                p.get("predicted_pnl", 0),
            )

            # Simulate close after 60 s with a small random PnL for PPO
            if ppo_hook and hasattr(ctx, "execution_result") and ctx.execution_result:
                import random
                import threading
                trade_id = ctx.execution_result.get("order_id", f"t_{int(time.time())}")

                class _FakeCtx:
                    status = "executed"
                    routed_order = type("r", (), {"symbol": symbol})()
                    entry_time = time.time()

                ppo_hook.on_trade_executed(_FakeCtx())

                def _close_later(tid, predicted):
                    time.sleep(60)
                    realized = predicted * random.uniform(0.7, 1.3)
                    ppo_hook.on_trade_closed(tid, realized)
                    stats.ppo_update()
                    logger.info("PPO updated | trade %s | realized $%.2f", tid, realized)

                threading.Thread(
                    target=_close_later,
                    args=(trade_id, p.get("predicted_pnl", 10.0)),
                    daemon=True,
                ).start()
        else:
            logger.debug("Pipeline REFUSED: %s", symbol)

    return handle_tick


# ---------------------------------------------------------------------------
# Status printer thread
# ---------------------------------------------------------------------------

def status_printer(orch, ppo_agent, stats: SessionStats,
                   deriv_ok: bool, mt5_ok: bool, stop_flag):
    while not stop_flag():
        time.sleep(30)
        stats.print_status(orch, ppo_agent, deriv_ok, mt5_ok)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ApexQuantumICT Demo Trading")
    parser.add_argument("--symbol", default="EURUSD", help="Symbol to trade (default: EURUSD)")
    parser.add_argument(
        "--mode", default="both",
        choices=["paper", "deriv", "mt5", "both"],
        help="Broker mode: paper (simulated), deriv, mt5, both (default: both)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  ApexQuantumICT — Live Demo Trading")
    print(f"  Symbol: {args.symbol}  |  Mode: {args.mode.upper()}")
    print(f"  Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Initialise pipeline orchestrator
    # ------------------------------------------------------------------
    logger.info("Initialising 20-stage pipeline orchestrator...")
    try:
        from trading.pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator()
        logger.info("Pipeline orchestrator ready")
    except Exception as exc:
        logger.error("Failed to init orchestrator: %s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Initialise PPO agent + hook
    # ------------------------------------------------------------------
    logger.info("Initialising PPO RL agent...")
    ppo_agent = None
    ppo_hook = None
    try:
        from trading.rl.scheduler_agent import PPOSchedulerAgent
        from trading.rl.ppo_paper_hook import PPOPaperHook
        ppo_agent = PPOSchedulerAgent()
        ppo_hook = PPOPaperHook(ppo_agent)
        logger.info("PPO agent ready (state_dim=166, buffer=%d)", ppo_agent.buffer.buffer_size)
    except Exception as exc:
        logger.warning("PPO not available: %s — continuing without ML feedback", exc)

    # ------------------------------------------------------------------
    # 3. Connect to brokers
    # ------------------------------------------------------------------
    deriv_broker = None
    mt5_broker = None
    deriv_ok = False
    mt5_ok = False

    if args.mode in ("deriv", "both"):
        logger.info("Connecting to Deriv demo...")
        try:
            from trading.brokers.deriv_broker import DerivBroker
            deriv_broker = DerivBroker()
            if deriv_broker.connect():
                deriv_ok = True
                # Deriv symbol for forex: frxEURUSD, frxGBPUSD, etc.
                deriv_symbol = "frx" + args.symbol if not args.symbol.startswith("frx") else args.symbol
                deriv_broker.subscribe_ticks(deriv_symbol)
                logger.info("Deriv demo connected — subscribed to %s", deriv_symbol)
            else:
                logger.warning("Deriv connection failed — check DERIV_API_TOKEN")
        except Exception as exc:
            logger.warning("Deriv unavailable: %s", exc)

    if args.mode in ("mt5", "both"):
        logger.info("Connecting to MT5 demo...")
        try:
            from trading.brokers.mt5_broker import MT5Broker
            mt5_broker = MT5Broker()
            if mt5_broker.connect(max_retries=3, retry_delay=2.0):
                mt5_ok = True
                logger.info("MT5 demo connected")
            else:
                logger.warning("MT5 connection failed — check MT5_ACCOUNT_ID / MT5_PASSWORD / MT5_SERVER")
        except Exception as exc:
            logger.warning("MT5 unavailable: %s", exc)

    # Paper mode: no real broker needed
    if args.mode == "paper":
        logger.info("Running in PAPER mode — no broker connection required")

    if args.mode in ("deriv", "mt5", "both") and not deriv_ok and not mt5_ok:
        logger.warning(
            "No broker connected. Falling back to paper mode with simulated ticks.\n"
            "Set DERIV_API_TOKEN / MT5_ACCOUNT_ID env vars to connect to real demo accounts."
        )
        args.mode = "paper"

    # ------------------------------------------------------------------
    # 4. Build tick accumulator + pipeline handler
    # ------------------------------------------------------------------
    accumulator = TickAccumulator(window=20, pipeline_interval=5.0, min_ticks=10)
    stats = SessionStats()

    pipeline_fn = build_pipeline_handler(
        orch, ppo_hook, accumulator, stats, args.symbol, args.mode
    )

    # ------------------------------------------------------------------
    # 5. Status printer (background thread)
    # ------------------------------------------------------------------
    _stopped = [False]
    status_thread = Thread(
        target=status_printer,
        args=(orch, ppo_agent, stats, deriv_ok, mt5_ok, lambda: _stopped[0]),
        daemon=True,
    )
    status_thread.start()

    # ------------------------------------------------------------------
    # 6. Run tick loop
    # ------------------------------------------------------------------
    if args.mode == "paper":
        # Simulated tick mode — generate synthetic ticks locally
        logger.info("Paper mode: generating simulated ticks for %s...", args.symbol)
        import random

        base_price = 1.0855
        try:
            while True:
                # Random walk tick
                base_price += random.uniform(-0.0002, 0.0002)
                pipeline_fn(("paper", base_price))
                time.sleep(0.05)  # 50 ms cadence → ~20 ticks/s
        except KeyboardInterrupt:
            pass
    else:
        # Real async tick loop from Deriv + MT5
        from trading.brokers.async_tick_loop import AsyncTickLoop

        tick_loop = AsyncTickLoop(
            pipeline_fn=pipeline_fn,
            queue_maxsize=1000,
            deriv_poll_interval=0.005,
            mt5_poll_interval=0.010,
        )

        async def _run():
            await tick_loop.run(
                deriv_broker=deriv_broker if deriv_ok else None,
                mt5_broker=mt5_broker if mt5_ok else None,
                symbol=args.symbol,
            )

        logger.info("Starting async tick loop for %s...", args.symbol)
        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            pass

    # ------------------------------------------------------------------
    # 7. Shutdown
    # ------------------------------------------------------------------
    _stopped[0] = True
    logger.info("Shutting down...")

    if deriv_broker and deriv_ok:
        try:
            deriv_broker.disconnect()
        except Exception:
            pass
    if mt5_broker and mt5_ok:
        try:
            mt5_broker.disconnect()
        except Exception:
            pass

    print("\n" + "=" * 60)
    stats.print_status(orch, ppo_agent, deriv_ok, mt5_ok)
    print("\nFinal latency stats:", tick_loop.get_latency_stats() if args.mode != "paper" else "N/A (paper mode)")
    print("Session complete.")


if __name__ == "__main__":
    main()
