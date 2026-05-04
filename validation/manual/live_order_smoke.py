"""
Quick live order routing test — Step 3 validation.
Places ONE real order on MT5 demo account via the pipeline with _paper_mode=False.
Run once, verify position appears in MetaTrader terminal, then Ctrl+C.
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("live_order_test")


def main():
    # 1. Connect MT5
    logger.info("Connecting to MT5...")
    from trading.brokers.mt5_broker import MT5Broker
    broker = MT5Broker()
    if not broker.connect(max_retries=3, retry_delay=2.0):
        logger.error("MT5 connection failed — check MT5_ACCOUNT_ID / MT5_PASSWORD / MT5_SERVER")
        sys.exit(1)

    info = broker.get_account_info()
    mode = info.get("trade_mode", "?") if info else "?"
    logger.info("MT5 connected — account %s @ %s | mode=%s | balance=%.2f",
                info.get("login"), info.get("server"), mode,
                info.get("balance", 0) if info else 0)

    # 2. Init orchestrator in LIVE mode
    logger.info("Initialising pipeline orchestrator (paper_mode=False)...")
    from trading.pipeline.orchestrator import PipelineOrchestrator
    orch = PipelineOrchestrator()
    orch._paper_mode = False   # ← triggers real order via Stage 16

    # 3. Resolve the broker-specific symbol name
    import MetaTrader5 as mt5
    base_symbol = "EURUSD"
    symbol = base_symbol
    if mt5.symbol_info(symbol) is None:
        for suffix in ("_r", "m", ".", "_micro", "_pro", "_ecn"):
            candidate = base_symbol + suffix
            if mt5.symbol_info(candidate) is not None:
                symbol = candidate
                logger.info("Resolved symbol: %s → %s", base_symbol, symbol)
                break

    # 4. Build a minimal OHLCV window using real MT5 bars
    logger.info("Fetching recent %s bars from MT5...", symbol)
    bars = broker.get_ohlcv(symbol, count=25)
    if len(bars) < 21:
        logger.error("Not enough bars returned (%d) for %s", len(bars), symbol)
        broker.disconnect()
        sys.exit(1)

    window = bars[-21:-1]   # 20 bars
    ohlcv = {
        "open":   [b["open"]   for b in window],
        "high":   [b["high"]   for b in window],
        "low":    [b["low"]    for b in window],
        "close":  [b["close"]  for b in window],
        "volume": [b["volume"] for b in window],
        "time":   [b["timestamp"] for b in window],
    }

    # 4. Run pipeline — Stage 16 will call mt5_broker.place_order()
    logger.info("Running 20-stage pipeline (live mode)...")
    from trading.brokers.mt5_broker import mt5_broker as _singleton
    # Make sure the singleton is the connected instance
    _singleton.connected = broker.connected
    _singleton.account = broker.account
    _singleton.password = broker.password
    _singleton.server = broker.server

    try:
        ctx = orch.execute(ohlcv, symbol=symbol, source="LIVE_TEST")
    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        broker.disconnect()
        sys.exit(1)

    decision = getattr(ctx, "collapse_decision", "REFUSED")
    logger.info("Pipeline decision: %s", decision)

    if decision == "AUTHORIZED" and ctx.proposal:
        p = ctx.proposal
        logger.info("Proposal: %s %s @ %.5f | SL %.5f | TP %.5f",
                    p.get("direction", "?").upper(), symbol,
                    p.get("entry", 0), p.get("stop", 0), p.get("target", 0))

        result = getattr(ctx, "execution_result", None)
        if result and result.get("status") == "filled":
            logger.info("ORDER PLACED — ticket/id: %s | entry: %.5f",
                        result.get("order_id"), result.get("entry_price", 0))
            logger.info("Check MetaTrader terminal for open position. Test PASSED.")
        else:
            logger.warning("Order was not filled. execution_result: %s", result)
    else:
        logger.info("Pipeline REFUSED this window — no order placed.")
        logger.info("This is normal if the collapse breaker sees insufficient signal.")
        logger.info("Try running again or wait for next tick window.")

    broker.disconnect()
    logger.info("Done.")


if __name__ == "__main__":
    main()
