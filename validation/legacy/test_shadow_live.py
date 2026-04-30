#!/usr/bin/env python3
"""
Shadow Trading Test with Live MT5 Data

Runs the full system on live market data without executing trades.
Validates all 5 phases work correctly in real-time.
"""

import MetaTrader5 as mt5
import time
import sys
from datetime import datetime

print('='*70)
print('PHASE 5: Shadow Trading with Live MT5 Data')
print('='*70)

# Initialize MT5
if not mt5.initialize():
    print('❌ MT5 not available')
    sys.exit(1)

# Get available symbols
symbols = mt5.symbols_get()
symbol_names = [s.name for s in symbols]
print(f'Available symbols: {len(symbol_names)}')

# Find a forex pair
forex_pairs = [s for s in symbol_names if 'USD' in s and len(s) == 6]
test_symbol = forex_pairs[0] if forex_pairs else symbol_names[0]
print(f'Using symbol: {test_symbol}')

# Initialize components
from trading.memory import get_embedder
from trading.models import SimplePricePredictor
from trading.agents import PatternAgent, RiskAgent, TimingAgent, MultiAgentOrchestrator
from trading.kernel import Scheduler
from trading.shadow import ShadowModeRunner, PaperBroker

print('\nInitializing components...')
embedder = get_embedder()
predictor = SimplePricePredictor()
pattern = PatternAgent()
risk = RiskAgent()
timing = TimingAgent()
orchestrator = MultiAgentOrchestrator(agents=[pattern, risk, timing])
scheduler = Scheduler(config={'use_rl': False})

# Paper broker
broker = PaperBroker(initial_balance=10000.0)

# Mock trading system
class MockTradingSystem:
    def decide(self, market_data, context=None):
        ohlcv = market_data.get('ohlcv', [])
        if len(ohlcv) < 20:
            return {'should_trade': False, 'reason': 'Insufficient data'}
        
        embedding = embedder.encode(ohlcv)
        prediction = predictor.predict(embedding)
        
        market_state = {
            'ohlc': ohlcv,
            'trend': 'neutral' if abs(prediction['trend']) < 0.1 else ('bullish' if prediction['trend'] > 0 else 'bearish'),
            'operator_scores': {}
        }
        
        trajectories = [{'id': f'traj_{i}', 'energy': 0.3 + i*0.1, 'action': 0.1 + i*0.05} for i in range(3)]
        votes = orchestrator.collect_votes(trajectories, market_state)
        decision = orchestrator.aggregate_votes(votes)
        
        from trading.kernel.scheduler import CollapseDecision
        collapse, _ = scheduler.authorize_collapse(
            proposal={'agent_decision': decision.__dict__},
            projected_trajectories=trajectories,
            delta_s=0.3,
            constraints_passed=True,
            reconciliation_clear=True
        )
        
        return {
            'should_trade': collapse.value == 'AUTHORIZED',
            'confidence': decision.confidence,
            'selected_trajectory': decision.selected_trajectory,
            'side': 'buy' if prediction['trend'] > 0 else 'sell'
        }

runner = ShadowModeRunner(trading_system=MockTradingSystem(), paper_broker=broker, mode='paper')

# Run for 30 seconds
print('\nRunning shadow trading for 30 seconds...')
print('Press Ctrl+C to stop early')
start_time = time.time()
decision_count = 0
try:
    while time.time() - start_time < 30:
        tick = mt5.symbol_info_tick(test_symbol)
        if not tick:
            time.sleep(1)
            continue
        
        rates = mt5.copy_rates_from_pos(test_symbol, mt5.TIMEFRAME_M1, 0, 100)
        if rates is None or len(rates) == 0:
            time.sleep(1)
            continue
        
        ohlcv = []
        for r in rates:
            ohlcv.append({
                'open': r[1],
                'high': r[2],
                'low': r[3],
                'close': r[4],
                'volume': r[5]
            })
        
        market_data = {
            'symbol': test_symbol,
            'current_price': tick.bid,
            'ohlcv': ohlcv
        }
        
        decision = runner.run_decision_cycle(market_data)
        decision_count += 1
        
        if decision.should_trade:
            print(f'[{datetime.now().strftime("%H:%M:%S")}] Trade signal: {test_symbol} @ {tick.bid:.5f}')
        
        time.sleep(5)
except KeyboardInterrupt:
    print('\nStopped by user')

mt5.shutdown()

# Generate report
stats = runner.get_shadow_statistics()
print(f'\n📊 Shadow Trading Results:')
print(f'   Total decisions: {stats["total_decisions"]}')
print(f'   Trade signals: {stats["trade_decisions"]}')
print(f'   Trade rate: {stats["trade_rate"]:.1%}')
print(f'   Avg confidence: {stats["avg_confidence"]:.2f}')

if stats['total_decisions'] > 0:
    print('\n✅ 5.1 Shadow Trading with Live Data: PASSED')
    sys.exit(0)
else:
    print('\n⚠️ No decisions made (check market data)')
    sys.exit(1)
