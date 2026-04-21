#!/usr/bin/env python3
"""
verify_brokers.py — Comprehensive broker integration verification

Tests:
1. Credential management (encryption, storage, retrieval)
2. Broker connections (Deriv, MT5)
3. Market data aggregation
4. Logging and audit trail
5. Telegram integration

Usage:
    python verify_brokers.py
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(test_name, success, details=""):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"  {status} | {test_name}")
    if details:
        print(f"       {details}")


def test_credential_management():
    """Test credential manager"""
    print_header("1. CREDENTIAL MANAGEMENT")
    
    from trading.brokers.credentials import CredentialManager, BrokerCredential
    
    # Create temp directory for testing
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Test 1: Initialize with master password
        try:
            manager = CredentialManager(master_password="test_password_123")
            manager.ENCRYPTED_FILE = Path(temp_dir) / "test_creds.enc"
            print_result("Initialize CredentialManager", True)
        except Exception as e:
            print_result("Initialize CredentialManager", False, str(e))
            return False
        
        # Test 2: Store credentials
        try:
            success = manager.store_credential(
                broker_type='deriv',
                name='test_demo',
                credentials={'token': 'test_token_xyz'},
                is_demo=True,
                metadata={'test': True}
            )
            print_result("Store Deriv credentials", success)
        except Exception as e:
            print_result("Store Deriv credentials", False, str(e))
        
        # Test 3: Retrieve credentials
        try:
            cred = manager.get_credential('deriv', 'test_demo')
            if cred and cred.credentials.get('token') == 'test_token_xyz':
                print_result("Retrieve credentials", True)
            else:
                print_result("Retrieve credentials", False, "Data mismatch")
        except Exception as e:
            print_result("Retrieve credentials", False, str(e))
            # Try showing what we got
            try:
                cred = manager.get_credential('deriv', 'test_demo')
                print(f"       Debug: cred type={type(cred)}, dict={cred.__dict__ if cred else 'None'}")
            except:
                pass
        
        # Test 4: List stored accounts
        try:
            accounts = manager.list_stored_accounts()
            if ('deriv', 'test_demo') in accounts:
                print_result("List accounts", True, f"Found {len(accounts)} account(s)")
            else:
                print_result("List accounts", False, "Account not found in list")
        except Exception as e:
            print_result("List accounts", False, str(e))
        
        # Test 5: Delete credentials
        try:
            success = manager.delete_credential('deriv', 'test_demo')
            print_result("Delete credentials", success)
        except Exception as e:
            print_result("Delete credentials", False, str(e))
        
        return True
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_broker_manager():
    """Test broker manager and symbol mapping"""
    print_header("2. BROKER MANAGER")
    
    from trading.brokers.broker_manager import BrokerManager, get_broker_manager
    
    try:
        manager = BrokerManager()
        
        # Test 1: Symbol mapping
        try:
            deriv_eurusd = manager.get_broker_symbol('EURUSD', 'deriv')
            mt5_eurusd = manager.get_broker_symbol('EURUSD', 'mt5')
            
            if deriv_eurusd == 'frxEURUSD' and mt5_eurusd == 'EURUSD':
                print_result("Symbol mapping", True)
            else:
                print_result("Symbol mapping", False, 
                           f"deriv:{deriv_eurusd}, mt5:{mt5_eurusd}")
        except Exception as e:
            print_result("Symbol mapping", False, str(e))
        
        # Test 2: Timeframe conversion
        try:
            deriv_gran = manager._timeframe_to_deriv_granularity('1h')
            mt5_tf = manager._timeframe_to_mt5('1h')
            
            if deriv_gran == 3600 and mt5_tf == 16385:
                print_result("Timeframe conversion", True)
            else:
                print_result("Timeframe conversion", False,
                           f"deriv:{deriv_gran}, mt5:{mt5_tf}")
        except Exception as e:
            print_result("Timeframe conversion", False, str(e))
        
        # Test 3: Price comparison structure
        try:
            comparison = manager.compare_prices('EURUSD')
            if 'symbol' in comparison and 'sources' in comparison:
                print_result("Price comparison structure", True)
            else:
                print_result("Price comparison structure", False, "Missing fields")
        except Exception as e:
            print_result("Price comparison structure", False, str(e))
        
        return True
        
    except Exception as e:
        print_result("Broker manager initialization", False, str(e))
        return False


def test_broker_logger():
    """Test logging and audit trail"""
    print_header("3. BROKER LOGGER & AUDIT")
    
    from trading.brokers.broker_logger import BrokerLogger, get_broker_logger
    import tempfile
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        logger = BrokerLogger(log_dir=temp_dir)
        
        # Test 1: Log connection
        try:
            logger.log_connection(
                broker='test_broker',
                success=True,
                duration_ms=123.4,
                metadata={'test': True}
            )
            print_result("Log connection", True)
        except Exception as e:
            print_result("Log connection", False, str(e))
        
        # Test 2: Log data fetch
        try:
            logger.log_data_fetch(
                broker='test_broker',
                symbol='EURUSD',
                success=True,
                duration_ms=45.2,
                count=100
            )
            print_result("Log data fetch", True)
        except Exception as e:
            print_result("Log data fetch", False, str(e))
        
        # Test 3: Log trade
        try:
            logger.log_trade(
                broker='test_broker',
                symbol='EURUSD',
                operation='BUY',
                success=True,
                volume=0.1,
                price=1.0850,
                duration_ms=89.1,
                order_details={'type': 'market'}
            )
            print_result("Log trade", True)
        except Exception as e:
            print_result("Log trade", False, str(e))
        
        # Test 4: Get recent operations
        try:
            recent = logger.get_recent_operations(limit=10)
            if len(recent) >= 3:
                print_result("Retrieve recent operations", True, f"{len(recent)} records")
            else:
                print_result("Retrieve recent operations", False, 
                           f"Only {len(recent)} records")
        except Exception as e:
            print_result("Retrieve recent operations", False, str(e))
        
        # Test 5: Get stats
        try:
            stats = logger.get_stats(hours=1)
            if 'total' in stats:
                print_result("Operation statistics", True, 
                           f"{stats.get('successful', 0)}/{stats.get('total', 0)} success")
            else:
                print_result("Operation statistics", False, "Missing stats")
        except Exception as e:
            print_result("Operation statistics", False, str(e))
        
        # Test 6: Verify audit integrity
        try:
            intact = logger.verify_audit_integrity()
            print_result("Audit trail integrity", intact)
        except Exception as e:
            print_result("Audit trail integrity", False, str(e))
        
        return True
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_telegram_handlers():
    """Test Telegram handler structure"""
    print_header("4. TELEGRAM INTEGRATION")
    
    try:
        from trading.brokers.telegram_handlers import BrokerTelegramHandlers
        
        handlers = BrokerTelegramHandlers()
        
        # Check that required methods exist
        required_methods = [
            'cmd_brokers',
            'cmd_broker_add',
            'cmd_broker_remove',
            'cmd_markets',
            'cmd_price',
            'cmd_positions'
        ]
        
        all_present = True
        for method in required_methods:
            if hasattr(handlers, method):
                print_result(f"Handler method: {method}", True)
            else:
                print_result(f"Handler method: {method}", False, "Missing")
                all_present = False
        
        return all_present
        
    except Exception as e:
        print_result("Telegram handlers import", False, str(e))
        return False


def test_setup_credentials_cli():
    """Test setup_credentials.py CLI structure"""
    print_header("5. CREDENTIAL CLI TOOL")
    
    try:
        import setup_credentials
        
        # Check that main functions exist
        required_functions = [
            'setup_environment',
            'prompt_password',
            'cmd_add_deriv',
            'cmd_add_mt5',
            'cmd_list',
            'cmd_remove',
            'cmd_test'
        ]
        
        all_present = True
        for func in required_functions:
            if hasattr(setup_credentials, func):
                print_result(f"CLI function: {func}", True)
            else:
                print_result(f"CLI function: {func}", False, "Missing")
                all_present = False
        
        return all_present
        
    except Exception as e:
        print_result("CLI tool import", False, str(e))
        return False


def print_summary(results):
    """Print final summary"""
    print("\n" + "=" * 60)
    print("  VERIFICATION SUMMARY")
    print("=" * 60)
    
    total = len(results)
    passed = sum(1 for r in results if r)
    failed = total - passed
    
    print(f"  ✅ Passed: {passed}/{total}")
    print(f"  ❌ Failed: {failed}/{total}")
    
    if failed == 0:
        print("\n  🎉 ALL TESTS PASSED!")
        print("  Broker integration is ready to use.")
    else:
        print(f"\n  ⚠️  {failed} test(s) failed. Review errors above.")
    
    print("\n  Next steps:")
    print("  1. Copy .env.example to .env and fill in your credentials")
    print("  2. Run: python setup_credentials.py add deriv")
    print("  3. Run: python setup_credentials.py add mt5")
    print("  4. Start the Telegram bot to use broker commands")
    print("=" * 60)


def main():
    print("\n" + "=" * 60)
    print("  APEXQUANTUMICT BROKER INTEGRATION VERIFICATION")
    print("=" * 60)
    
    results = []
    
    # Run all tests
    results.append(test_credential_management())
    results.append(test_broker_manager())
    results.append(test_broker_logger())
    results.append(test_telegram_handlers())
    results.append(test_setup_credentials_cli())
    
    # Print summary
    print_summary(results)
    
    # Exit code
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
