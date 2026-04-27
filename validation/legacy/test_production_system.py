"""
Production System Test
Comprehensive test of production-ready trading system
Tests all new components: TradingView, Risk, Paper Trading, Monitoring, Resilience
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_phase1_tradingview():
    """Test Phase 1: TradingView Components"""
    print("\n" + "="*60)
    print("PHASE 1: TradingView Integration")
    print("="*60)
    
    try:
        # Test Pine Script exists
        pine_path = "trading/brokers/tradingview_pine.pine"
        assert os.path.exists(pine_path), f"Pine Script not found: {pine_path}"
        print("[PASS] Pine Script file exists")
        
        # Test TradingView Connector
        from trading.brokers.tradingview_connector import (
            TradingViewConnector, TradingViewSignal, get_tradingview_connector
        )
        connector = get_tradingview_connector()
        print("[PASS] TradingViewConnector created")
        
        # Test Signal Router
        from trading.brokers.signal_router import (
            SignalRouter, SymbolMapper, BrokerType, get_signal_router
        )
        router = get_signal_router()
        print("[PASS] SignalRouter created")
        
        # Test symbol mapping
        deriv_symbol = SymbolMapper.to_deriv('EURUSD')
        assert deriv_symbol == 'frxEURUSD', f"Symbol mapping failed: {deriv_symbol}"
        print("[PASS] Symbol mapping works")
        
        # Test synthetic detection
        assert SymbolMapper.is_synthetic('R_10'), "Synthetic detection failed"
        print("[PASS] Synthetic detection works")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Phase 1: {e}")
        return False


def test_phase2_risk():
    """Test Phase 2: Risk Management"""
    print("\n" + "="*60)
    print("PHASE 2: Risk Management")
    print("="*60)
    
    try:
        # Test Risk Manager
        from trading.risk.risk_manager import (
            ProductionRiskManager, RiskCheck, RiskLevel, get_risk_manager
        )
        rm = get_risk_manager(daily_loss_limit=100.0, max_position_size=0.1)
        print("[PASS] RiskManager created")
        
        # Test risk check
        check = rm.check_all_limits('EURUSD', 'buy', 0.05, 1.0850)
        assert check.passed, f"Risk check failed: {check.message}"
        print("[PASS] Risk check passed")
        
        # Test position sizer
        from trading.risk.position_sizer import (
            PositionSizer, SizingParams, get_position_sizer
        )
        sizer = get_position_sizer()
        print("[PASS] PositionSizer created")
        
        # Test Kelly calculation
        kelly = sizer.kelly_criterion(win_rate=0.6, avg_win=150, avg_loss=100)
        assert 0 < kelly < 0.5, f"Kelly calculation invalid: {kelly}"
        print(f"[PASS] Kelly Criterion: {kelly:.2%}")
        
        # Test PnL Tracker
        from trading.risk.pnl_tracker import (
            DailyPnLTracker, TradeRecord, get_pnl_tracker
        )
        tracker = get_pnl_tracker()
        print("[PASS] PnLTracker created")
        
        # Test trade recording
        trade = TradeRecord(
            trade_id="test_001",
            symbol="EURUSD",
            direction="buy",
            entry_price=1.0850,
            exit_price=1.0860,
            size=0.1,
            realized_pnl=10.0,
            entry_time=time.time() - 3600,
            exit_time=time.time(),
            broker="deriv"
        )
        tracker.record_trade(trade)
        print("[PASS] Trade recorded")
        
        stats = tracker.get_daily_stats()
        assert stats.get('daily_pnl') == 10.0 or stats.get('total_pnl') == 10.0, f"PnL tracking failed: {stats}"
        print("[PASS] PnL tracking correct")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Phase 2: {e}")
        return False


def test_phase3_paper_trading():
    """Test Phase 3: Paper Trading"""
    print("\n" + "="*60)
    print("PHASE 3: Paper Trading")
    print("="*60)
    
    try:
        # Test Demo Orchestrator
        from trading.brokers.demo_orchestrator import (
            DemoOrchestrator, DemoStatus, get_demo_orchestrator
        )
        orch = get_demo_orchestrator(paper_mode_enforced=True)
        print("[PASS] DemoOrchestrator created")
        
        status = orch.get_status()
        assert status['paper_mode_enforced'], "Paper mode not enforced"
        print("[PASS] Paper mode enforced")
        
        # Test Paper Trading Loop
        from trading.paper_trading_loop import PaperTradingLoop, get_paper_trading_loop
        loop = get_paper_trading_loop(enable_taep=False)
        print("[PASS] PaperTradingLoop created")
        
        # Test Backtest Logger
        from trading.backtest_logger import (
            BacktestLogger, TradeLog, get_backtest_logger
        )
        logger_inst = get_backtest_logger(session_name="test_session")
        print("[PASS] BacktestLogger created")
        
        # Test trade logging
        trade = TradeLog(
            trade_id="bt_001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="EURUSD",
            direction="buy",
            entry_price=1.0850,
            exit_price=1.0860,
            size=0.1,
            realized_pnl=10.0,
            return_pct=0.1,
            broker="deriv",
            duration_seconds=300.0,
            entry_signal="RSI",
            exit_reason="TP",
            taep_authorized=True,
            taep_decision="ACCEPT",
            risk_check_passed=True,
            max_drawdown_during_trade=-5.0,
            entry_rsi=30.0,
            entry_ofi=100.0,
            entry_volatility=0.01,
            tags=["test"],
            notes="Test trade"
        )
        logger_inst.log_trade(trade)
        print("[PASS] Backtest trade logged")
        
        # Test metrics calculation
        metrics = logger_inst.calculate_metrics()
        assert 'summary' in metrics, "Metrics calculation failed"
        print(f"[PASS] Metrics calculated: {metrics['summary']['total_trades']} trades")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Phase 3: {e}")
        return False


def test_phase4_monitoring():
    """Test Phase 4: Monitoring"""
    print("\n" + "="*60)
    print("PHASE 4: Monitoring")
    print("="*60)
    
    try:
        # Test Health Check Service
        from trading.monitoring.health_check import (
            HealthCheckService, HealthStatus, get_health_service
        )
        service = get_health_service()
        print("[PASS] HealthCheckService created")
        
        # Perform manual check
        health = service.get_current_health()
        assert len(health) > 0, "Health check returned empty"
        print("[PASS] Health checks executed")
        
        # Check overall status
        overall = service.get_overall_status()
        print(f"[INFO] Overall health: {overall.value}")
        
        # Test Dashboard (without running it)
        from trading.monitoring.dashboard import TradingDashboard
        print("[PASS] Dashboard class available")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Phase 4: {e}")
        return False


def test_phase5_resilience():
    """Test Phase 5: Resilience"""
    print("\n" + "="*60)
    print("PHASE 5: Resilience")
    print("="*60)
    
    try:
        # Test Circuit Breaker
        from trading.resilience.circuit_breaker import (
            CircuitBreaker, CircuitBreakerConfig, CircuitState,
            get_circuit_breaker, get_circuit_breaker_manager
        )
        
        manager = get_circuit_breaker_manager()
        breaker = get_circuit_breaker("test_service")
        print("[PASS] CircuitBreaker created")
        
        # Test successful calls
        def success_func():
            return "success"
        
        for i in range(3):
            ok, result = breaker.call(success_func)
            assert ok, f"Success call {i} failed"
        print("[PASS] Circuit breaker allows successful calls")
        
        # Test state
        status = breaker.get_status()
        assert status['state'] == 'closed', f"Unexpected state: {status['state']}"
        print("[PASS] Circuit breaker state correct")
        
        # Test State Recovery
        from trading.resilience.state_recovery import (
            StateRecovery, SystemState, get_state_recovery
        )
        recovery = get_state_recovery()
        print("[PASS] StateRecovery created")
        
        # Test state save
        recovery.save_state(reason="test")
        print("[PASS] State saved")
        
        # Test state restore
        restored = recovery.restore_state()
        print("[PASS] State restore attempted")
        
        # Test status
        status = recovery.get_status()
        assert status['saves_performed'] > 0, "State save not recorded"
        print("[PASS] State recovery status correct")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Phase 5: {e}")
        return False


def test_integration():
    """Test full integration"""
    print("\n" + "="*60)
    print("INTEGRATION TEST")
    print("="*60)
    
    try:
        # Test all components can be imported together
        from trading.brokers import (
            TradingViewConnector, SignalRouter, DemoOrchestrator,
            get_tradingview_connector, get_signal_router, get_demo_orchestrator
        )
        from trading.risk import (
            ProductionRiskManager, PositionSizer, DailyPnLTracker,
            get_risk_manager, get_position_sizer, get_pnl_tracker
        )
        from trading.monitoring import (
            HealthCheckService, get_health_service
        )
        from trading.resilience import (
            CircuitBreaker, StateRecovery,
            get_circuit_breaker, get_state_recovery
        )
        print("[PASS] All imports successful")
        
        # Test singleton pattern
        tv1 = get_tradingview_connector()
        tv2 = get_tradingview_connector()
        assert tv1 is tv2, "TradingView connector not singleton"
        print("[PASS] Singleton pattern working")
        
        # Test paper mode enforcement
        orch = get_demo_orchestrator()
        assert orch.paper_mode_enforced, "Paper mode not enforced"
        print("[PASS] Paper mode enforced across system")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Integration: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all production system tests"""
    print("="*60)
    print("PRODUCTION SYSTEM VERIFICATION")
    print("Testing all 5 phases of implementation")
    print("="*60)
    
    results = {
        'Phase 1: TradingView': test_phase1_tradingview(),
        'Phase 2: Risk': test_phase2_risk(),
        'Phase 3: Paper Trading': test_phase3_paper_trading(),
        'Phase 4: Monitoring': test_phase4_monitoring(),
        'Phase 5: Resilience': test_phase5_resilience(),
        'Integration': test_integration()
    }
    
    # Summary
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {passed}/{total} passed ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n" + "="*60)
        print("ALL TESTS PASSED - SYSTEM PRODUCTION READY")
        print("="*60)
        return 0
    else:
        print("\n" + "="*60)
        print("SOME TESTS FAILED - REVIEW REQUIRED")
        print("="*60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
