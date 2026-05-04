"""
Pre-Flight Check Script
Verify system ready for paper trading demo
"""

import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_broker_connections():
    """Verify Deriv and MT5 connections"""
    print("\n" + "="*60)
    print("CHECK 1: Broker Connections")
    print("="*60)
    
    from trading.brokers.deriv_broker import DerivBroker
    from trading.brokers.mt5_broker import MT5Broker
    
    deriv_ok = False
    mt5_ok = False
    
    # Check Deriv
    try:
        deriv = DerivBroker()
        if deriv.connect():
            info = deriv.get_account_info()
            if info:
                print(f"[PASS] Deriv Connected: Account {info.get('login', 'N/A')}")
                print(f"       Balance: ${info.get('balance', 0):.2f}")
                deriv_ok = True
            else:
                print("[WARN] Deriv connected but no account info")
        else:
            print("[FAIL] Deriv connection failed")
    except Exception as e:
        print(f"[FAIL] Deriv error: {e}")
    
    # Check MT5
    try:
        mt5 = MT5Broker()
        if mt5.connect():
            info = mt5.get_account_info()
            if info:
                print(f"[PASS] MT5 Connected: Account {info.get('login', 'N/A')}")
                print(f"       Balance: ${info.get('balance', 0):.2f}")
                mt5_ok = True
            else:
                print("[WARN] MT5 connected but no account info")
        else:
            print("[FAIL] MT5 connection failed")
    except Exception as e:
        print(f"[FAIL] MT5 error: {e}")
    
    return deriv_ok or mt5_ok  # At least one broker needed


def check_paper_mode():
    """Verify paper mode is enforced"""
    print("\n" + "="*60)
    print("CHECK 2: Paper Mode Enforcement")
    print("="*60)
    
    from trading.brokers.demo_orchestrator import get_demo_orchestrator
    
    try:
        orch = get_demo_orchestrator(paper_mode_enforced=True)
        status = orch.get_status()
        
        if status['paper_mode_enforced']:
            print("[PASS] Paper mode ENFORCED - No live trading possible")
            print(f"[INFO] Paper mode verified: {status['paper_mode_verified']}")
            return True
        else:
            print("[FAIL] Paper mode NOT enforced!")
            return False
    except Exception as e:
        print(f"[FAIL] Paper mode check error: {e}")
        return False


def check_risk_limits():
    """Verify risk limits configured"""
    print("\n" + "="*60)
    print("CHECK 3: Risk Limits")
    print("="*60)
    
    from trading.risk.risk_manager import get_risk_manager
    
    try:
        rm = get_risk_manager()
        status = rm.get_status()
        
        print(f"[INFO] Daily Loss Limit: ${status.get('daily_loss_limit', 0):.2f}")
        print(f"[INFO] Max Position Size: {status.get('max_position_size', 0)} lots")
        print(f"[INFO] Current Daily PnL: ${status.get('daily_pnl', 0):.2f}")
        print(f"[INFO] Remaining Limit: ${status.get('remaining_limit', 0):.2f}")
        print(f"[INFO] Kill Switch: {'ACTIVE' if status.get('kill_switch') else 'Inactive'}")
        print(f"[INFO] Risk Level: {status.get('level', 'unknown').upper()}")
        
        return status.get('level') == 'green'
    except Exception as e:
        print(f"[FAIL] Risk check error: {e}")
        return False


def clear_stale_state():
    """Clear any stale state from previous runs"""
    print("\n" + "="*60)
    print("CHECK 4: Clear Stale State")
    print("="*60)
    
    import shutil
    from pathlib import Path
    
    # Clear old state files
    state_dirs = [
        "trading_data/state",
        "trading_data/pnl",
        "trading_data/backtests"
    ]
    
    for dir_path in state_dirs:
        try:
            path = Path(dir_path)
            if path.exists():
                # Keep directory, clear files
                for file in path.glob("*.json"):
                    file.unlink()
                print(f"[OK] Cleared: {dir_path}")
            else:
                path.mkdir(parents=True, exist_ok=True)
                print(f"[OK] Created: {dir_path}")
        except Exception as e:
            print(f"[WARN] Could not clear {dir_path}: {e}")
    
    return True


def initialize_backtest_logger():
    """Initialize fresh backtest logger session"""
    print("\n" + "="*60)
    print("CHECK 5: Initialize Backtest Logger")
    print("="*60)
    
    from trading.backtest_logger import get_backtest_logger
    from datetime import datetime
    
    try:
        session_name = f"paper_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger = get_backtest_logger(session_name=session_name)
        status = logger.get_status()
        
        print(f"[PASS] Backtest logger initialized: {session_name}")
        print(f"[INFO] Session dir: {status['session_dir']}")
        
        return True
    except Exception as e:
        print(f"[FAIL] Logger init error: {e}")
        return False


def main():
    """Run all pre-flight checks"""
    print("="*60)
    print("PRE-FLIGHT CHECKS - Paper Trading Demo")
    print("="*60)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: PAPER TRADING (Live trading disabled)")
    
    results = {
        'Brokers': check_broker_connections(),
        'Paper Mode': check_paper_mode(),
        'Risk Limits': check_risk_limits(),
        'State Clear': clear_stale_state(),
        'Logger Init': initialize_backtest_logger()
    }
    
    # Summary
    print("\n" + "="*60)
    print("PRE-FLIGHT SUMMARY")
    print("="*60)
    
    all_passed = all(results.values())
    
    for check, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check}")
    
    if all_passed:
        print("\n" + "="*60)
        print("ALL CHECKS PASSED - READY FOR PAPER TRADING")
        print("="*60)
        return 0
    else:
        print("\n" + "="*60)
        print("SOME CHECKS FAILED - REVIEW REQUIRED")
        print("="*60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
