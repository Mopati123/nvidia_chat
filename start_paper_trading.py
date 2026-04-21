"""
Paper Trading Demo - Component Startup
Starts all required components for live paper trading
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Track running components
components = {}


def start_health_monitoring():
    """Start health check service"""
    logger.info("Starting Health Monitoring Service...")
    
    from trading.monitoring.health_check import get_health_service
    
    service = get_health_service(check_interval=30)
    service.start()
    
    components['health'] = service
    logger.info("✅ Health monitoring started (30s interval)")
    return service


def start_paper_trading_loop():
    """Start paper trading loop"""
    logger.info("Starting Paper Trading Loop...")
    
    from trading.paper_trading_loop import get_paper_trading_loop
    
    loop = get_paper_trading_loop(enable_taep=True)
    loop.start()
    
    components['paper_loop'] = loop
    logger.info("✅ Paper trading loop started")
    return loop


def start_tradingview_webhook():
    """Start TradingView webhook server"""
    logger.info("Starting TradingView Webhook Server...")
    
    from trading.brokers.tradingview_connector import get_tradingview_connector
    
    connector = get_tradingview_connector()
    
    # Start in background thread
    def run_webhook():
        try:
            connector.start()
        except Exception as e:
            logger.error(f"Webhook server error: {e}")
    
    thread = threading.Thread(target=run_webhook, daemon=True)
    thread.start()
    
    components['webhook'] = connector
    logger.info("✅ TradingView webhook server started on port 5000")
    return connector


def generate_simulated_signals():
    """Generate simulated TradingView signals for demo"""
    logger.info("Starting Simulated Signal Generator...")
    
    from trading.brokers.tradingview_connector import TradingViewSignal
    from trading.brokers.signal_router import get_signal_router
    import random
    
    router = get_signal_router()
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
    signals = ['BUY', 'SELL', 'NONE']
    
    def signal_generator():
        """Generate random signals periodically"""
        signal_count = 0
        max_signals = 20  # Generate 20 signals for demo
        
        while signal_count < max_signals:
            try:
                time.sleep(3)  # Signal every 3 seconds
                
                # Create simulated signal
                signal = TradingViewSignal(
                    symbol=random.choice(symbols),
                    timeframe='1m',
                    price=1.0850 + random.uniform(-0.01, 0.01),
                    signal=random.choice(signals),
                    rsi=random.uniform(20, 80),
                    ofi=random.uniform(-200, 200),
                    microprice=1.0850 + random.uniform(-0.001, 0.001),
                    in_killzone=random.choice([True, False]),
                    timestamp=time.time(),
                    raw_data={'source': 'simulated'}
                )
                
                # Route signal
                order = router.route_signal(signal)
                
                if order:
                    logger.info(f"🎯 SIGNAL: {signal.symbol} {signal.signal} @ {signal.price:.5f}")
                    signal_count += 1
                
            except Exception as e:
                logger.error(f"Signal generation error: {e}")
        
        logger.info(f"✅ Signal generation complete: {signal_count} signals generated")
    
    thread = threading.Thread(target=signal_generator, daemon=True)
    thread.start()
    
    components['signal_gen'] = thread
    logger.info("✅ Simulated signal generator started")


def print_system_status():
    """Print current system status"""
    print("\n" + "="*60)
    print("SYSTEM STATUS")
    print("="*60)
    
    # Health status
    if 'health' in components:
        health = components['health'].get_overall_status()
        print(f"Health: {health.value.upper()}")
    
    # Paper trading status
    if 'paper_loop' in components:
        loop = components['paper_loop']
        status = loop.get_status()
        print(f"Paper Trading: {'Running' if status['running'] else 'Stopped'}")
        print(f"  Queue Size: {status['queue_size']}")
        print(f"  Active Trades: {status['active_trades']}")
        print(f"  Daily PnL: ${status['daily_pnl']:.2f}")
    
    print("="*60 + "\n")


def main():
    """Main startup sequence"""
    print("="*60)
    print("PAPER TRADING DEMO - Component Startup")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Mode: PAPER TRADING (No live execution)")
    print("="*60 + "\n")
    
    try:
        # 1. Start health monitoring
        start_health_monitoring()
        time.sleep(1)
        
        # 2. Start paper trading loop
        start_paper_trading_loop()
        time.sleep(1)
        
        # 3. Start TradingView webhook (optional - for external signals)
        # start_tradingview_webhook()
        # time.sleep(1)
        
        # 4. Start simulated signal generator
        generate_simulated_signals()
        time.sleep(1)
        
        print("\n" + "="*60)
        print("ALL COMPONENTS STARTED SUCCESSFULLY")
        print("="*60)
        
        # Monitor for 2 minutes
        print("\nMonitoring for 2 minutes (press Ctrl+C to stop)...\n")
        
        start_time = time.time()
        while time.time() - start_time < 120:  # 2 minutes
            print_system_status()
            time.sleep(30)
        
        print("\n" + "="*60)
        print("PAPER TRADING DEMO COMPLETE")
        print("="*60)
        
        # Shutdown gracefully
        if 'paper_loop' in components:
            components['paper_loop'].stop()
        if 'health' in components:
            components['health'].stop()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nShutdown requested...")
        
        # Graceful shutdown
        if 'paper_loop' in components:
            components['paper_loop'].stop()
        if 'health' in components:
            components['health'].stop()
        
        print("✅ Components stopped gracefully")
        return 0
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
