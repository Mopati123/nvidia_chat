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
    python -m scripts.broker.add_deriv_quick
    python -m scripts.broker.add_mt5_quick

    # Run:
    python -m scripts.trading.run_demo_trading [--symbol EURUSD] [--mode paper|deriv|mt5|both]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import pathlib
import signal
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
                            stats: SessionStats, symbol: str, mode: str,
                            csv_writer=None, csv_file=None,
                            live_mode: bool = False, mt5_broker_ref=None,
                            start_equity: float = 0.0, max_loss: float = 20.0,
                            trade_cooldown: float = 300.0):
    """Returns the function passed to AsyncTickLoop as pipeline_fn."""
    import MetaTrader5 as _mt5_api
    from trading.brokers.mt5_broker import mt5_position_tracker as _tracker

    _last_trade_time = [0.0]  # mutable so inner function can update it

    def handle_tick(source_tick: Tuple[str, Any]) -> None:
        source, tick = source_tick
        stats.tick()

        # Equity safety stop — check every 20 ticks to avoid hammering the broker API
        if live_mode and mt5_broker_ref and stats.ticks_received % 20 == 0 and start_equity > 0:
            acct = mt5_broker_ref.get_account_info()
            if acct:
                session_loss = start_equity - acct.get("equity", start_equity)
                if session_loss >= max_loss:
                    logger.error(
                        "EQUITY SAFETY STOP — session loss $%.2f >= limit $%.0f. Shutting down.",
                        session_loss, max_loss,
                    )
                    os.kill(os.getpid(), signal.SIGINT)
                    return

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

        # Live mode gates: skip pipeline if an open position exists or cooldown active
        if live_mode:
            if (time.time() - _last_trade_time[0]) < trade_cooldown:
                return  # within cooldown window
            open_positions = _mt5_api.positions_get()
            if open_positions and len(open_positions) > 0:
                logger.debug("Skipping pipeline — %d position(s) already open", len(open_positions))
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

            # Log trade to CSV
            if csv_writer:
                ticket = "paper"
                if hasattr(ctx, "execution_result") and ctx.execution_result:
                    ticket = ctx.execution_result.get("order_id", "paper")
                csv_writer.writerow({
                    "time": datetime.now().isoformat(),
                    "symbol": symbol,
                    "direction": p.get("direction", ""),
                    "entry": p.get("entry", 0),
                    "stop": p.get("stop", 0),
                    "target": p.get("target", 0),
                    "size": p.get("size", 0),
                    "ticket": ticket,
                    "predicted_pnl": p.get("predicted_pnl", 0),
                    "source": source,
                })
                if csv_file:
                    csv_file.flush()

            # Record trade time for cooldown
            if live_mode and hasattr(ctx, "execution_result") and ctx.execution_result:
                _last_trade_time[0] = time.time()

            # Register position with MT5 close tracker — real PnL feeds PPO on close
            if ppo_hook and hasattr(ctx, "execution_result") and ctx.execution_result:
                import threading as _threading
                trade_id  = ctx.execution_result.get("order_id", f"t_{int(time.time())}")
                predicted = p.get("predicted_pnl", 10.0)

                _selected_path    = getattr(ctx, 'selected_path', {}) or {}
                _action_weights   = getattr(ctx, 'action_weights', {}) or {}
                _memory_embedding = getattr(ctx, 'memory_embedding', None)

                class _FakeCtx:
                    status        = "executed"
                    routed_order  = type("r", (), {"symbol": symbol})()
                    entry_time    = time.time()
                    selected_path = _selected_path
                    action_weights = _action_weights
                    operator_scores = _selected_path   # O1–O18 embedded in selected_path
                    memory_embedding = _memory_embedding

                ppo_hook.on_trade_executed(_FakeCtx())

                def _ppo_callback(tid: str, realized: float) -> None:
                    ppo_hook.on_trade_closed(tid, realized)
                    stats.ppo_update()
                    logger.info("PPO updated | trade %s | realized $%.2f", tid, realized)

                if live_mode and mt5_broker_ref is not None:
                    try:
                        ticket_int = int(ctx.execution_result.get("order_id", ""))
                        _tracker.track(ticket_int, trade_id, _ppo_callback,
                                       predicted_pnl=predicted)
                    except (ValueError, TypeError):
                        # Non-numeric ID (Deriv contract) — fall back to instant callback
                        _threading.Thread(
                            target=_ppo_callback, args=(trade_id, predicted), daemon=True
                        ).start()
                else:
                    # Paper mode: fire immediately with predicted PnL
                    _threading.Thread(
                        target=_ppo_callback, args=(trade_id, predicted), daemon=True
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
    parser.add_argument("--live-demo", action="store_true",
                        help="Place real orders on demo account (default: paper signals only)")
    parser.add_argument("--lot-size", type=float, default=0.01,
                        help="Position size in lots for live-demo mode (default: 0.01)")
    parser.add_argument("--max-loss", type=float, default=20.0,
                        help="Session equity drawdown limit in USD before auto-stop (default: $20)")
    args = parser.parse_args()

    print("=" * 60)
    print("  ApexQuantumICT — Live Demo Trading")
    print(f"  Symbol: {args.symbol}  |  Mode: {args.mode.upper()}")
    if args.live_demo:
        print(f"  LIVE DEMO: real orders | lot={args.lot_size} | max-loss=${args.max_loss}")
    print(f"  Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Initialise pipeline orchestrator
    # ------------------------------------------------------------------
    logger.info("Initialising 20-stage pipeline orchestrator...")
    try:
        from trading.pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator()
        # paper_mode is set after broker connection (needs mt5_ok + --live-demo flag)
        # Apply lot size directly to risk manager NOW (env var set after init has no effect)
        if args.live_demo:
            orch.risk_manager.max_position_size = args.lot_size
            logger.info("Risk manager: max_position_size set to %.2f lots", args.lot_size)
        logger.info("Pipeline orchestrator initialised")
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
                from trading.brokers.mt5_broker import mt5_position_tracker as _tracker
                _tracker.start()
                logger.info("MT5 position close tracker started")
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

    # Set paper_mode: live-demo + MT5 connected = real orders; everything else = paper
    live_mode = args.live_demo and mt5_ok
    orch._paper_mode = not live_mode
    logger.info("Pipeline paper_mode=%s%s", orch._paper_mode,
                " (LIVE DEMO — real orders)" if live_mode else "")

    # Live-demo setup: sync singleton so Stage 16 can call place_order, capture start equity
    start_equity: float = 0.0
    if live_mode:
        from trading.brokers.mt5_broker import mt5_broker as _mt5_singleton
        _mt5_singleton.connected = True          # Stage 16 checks this flag
        os.environ["MAX_POSITION_SIZE"] = str(args.lot_size)
        acct = mt5_broker.get_account_info()
        start_equity = acct.get("equity", 0.0) if acct else 0.0
        logger.info("LIVE DEMO ready — lot=%.2f | start equity=$%.2f | session loss limit=$%.0f",
                    args.lot_size, start_equity, args.max_loss)

    # ------------------------------------------------------------------
    # 4. CSV trade log + tick accumulator + pipeline handler
    # ------------------------------------------------------------------
    _log_dir = pathlib.Path("logs")
    _log_dir.mkdir(exist_ok=True)
    _log_path = _log_dir / f"demo_trades_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    _csv_file = open(_log_path, "w", newline="")
    _writer = csv.DictWriter(_csv_file, fieldnames=[
        "time", "symbol", "direction", "entry", "stop", "target",
        "size", "ticket", "predicted_pnl", "source",
    ])
    _writer.writeheader()
    logger.info("Trade log: %s", _log_path)

    # In live mode: longer pipeline interval (60s) to avoid over-trading on micro-movements
    _pipeline_interval = 60.0 if live_mode else 5.0
    accumulator = TickAccumulator(window=20, pipeline_interval=_pipeline_interval, min_ticks=10)
    stats = SessionStats()

    pipeline_fn = build_pipeline_handler(
        orch, ppo_hook, accumulator, stats, args.symbol, args.mode,
        csv_writer=_writer, csv_file=_csv_file,
        live_mode=live_mode, mt5_broker_ref=mt5_broker if live_mode else None,
        start_equity=start_equity, max_loss=args.max_loss,
        trade_cooldown=300.0,  # 5 min minimum between trades in live mode
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

    try:
        _csv_file.close()
        logger.info("Trade log saved: %s", _log_path)
    except Exception:
        pass

    print("\n" + "=" * 60)
    stats.print_status(orch, ppo_agent, deriv_ok, mt5_ok)
    print("\nFinal latency stats:", tick_loop.get_latency_stats() if args.mode != "paper" else "N/A (paper mode)")
    print("Session complete.")


if __name__ == "__main__":
    main()
