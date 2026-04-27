#!/usr/bin/env python3
"""
setup_credentials.py — CLI tool for managing broker credentials

Usage:
    python -m scripts.broker.setup_credentials add deriv
    python -m scripts.broker.setup_credentials add mt5
    python -m scripts.broker.setup_credentials list
    python -m scripts.broker.setup_credentials remove <broker> <name>
    python -m scripts.broker.setup_credentials test <broker> <name>
"""

import os
import sys
import argparse
import json
import time
import locale
import uuid
from getpass import getpass
from typing import Optional

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# #region agent log
try:
    with open("logs/debug-3c812d.log", "a", encoding="utf-8") as _dbg:
        _dbg.write(json.dumps({
            "sessionId": "3c812d",
            "runId": "pre-fix",
            "hypothesisId": "H11",
            "id": f"log_{uuid.uuid4().hex}",
            "location": "setup_credentials.py:module_init",
            "message": "console_encoding_configured",
            "data": {
                "stdout_encoding": getattr(sys.stdout, "encoding", None),
                "stderr_encoding": getattr(sys.stderr, "encoding", None),
                "preferred_encoding": locale.getpreferredencoding(False)
            },
            "timestamp": int(time.time() * 1000)
        }) + "\n")
except Exception:
    pass
# #endregion

from trading.brokers.credentials import get_credential_manager, CredentialManager


def setup_environment():
    """Load .env file if present"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def prompt_password() -> str:
    """Prompt for master password if not set"""
    password = os.environ.get('APEX_CREDENTIAL_PASSWORD')
    if not password:
        password = getpass("Enter master password for credential encryption: ")
        confirm = getpass("Confirm password: ")
        if password != confirm:
            print("❌ Passwords do not match!")
            sys.exit(1)
    return password


def cmd_add_deriv(args):
    """Add Deriv.com credentials"""
    print("\n🔐 Adding Deriv.com API credentials")
    print("-" * 50)
    
    name = input("Credential name (e.g., 'demo', 'live'): ").strip() or "default"
    token = getpass("API Token (from app.deriv.com/account/api-token): ")
    
    if not token:
        print("❌ API token is required!")
        return False
    
    is_demo = input("Is this a demo account? [Y/n]: ").strip().lower() != 'n'
    
    manager = get_credential_manager(prompt_password())
    
    success = manager.store_credential(
        broker_type='deriv',
        name=name,
        credentials={'token': token},
        is_demo=is_demo,
        metadata={'added_via': 'cli'}
    )
    
    if success:
        print(f"✅ Deriv credentials '{name}' stored securely")
        
        # Test connection
        print("\n🧪 Testing connection...")
        ok, msg = manager.test_credential('deriv', name)
        if ok:
            print(f"✅ {msg}")
        else:
            print(f"⚠️  Test failed: {msg}")
            print("   Credentials saved but may be invalid")
        return True
    else:
        print("❌ Failed to store credentials")
        return False


def cmd_add_mt5(args):
    """Add MetaTrader 5 credentials"""
    print("\n🔐 Adding MetaTrader 5 credentials")
    print("-" * 50)
    
    name = input("Credential name (e.g., 'broker1', 'icmarkets'): ").strip() or "default"
    
    account_str = input("Account ID (login number): ").strip()
    if not account_str.isdigit():
        print("❌ Account ID must be a number!")
        return False
    
    password = getpass("Password: ")
    server = input("Server (e.g., 'ICMarketsSC-Demo', 'MetaQuotes-Demo'): ").strip()
    
    if not server:
        print("❌ Server name is required!")
        return False
    
    is_demo = input("Is this a demo account? [Y/n]: ").strip().lower() != 'n'
    
    manager = get_credential_manager(prompt_password())
    
    success = manager.store_credential(
        broker_type='mt5',
        name=name,
        account_id=account_str,
        credentials={
            'password': password,
            'server': server
        },
        is_demo=is_demo,
        metadata={'added_via': 'cli'}
    )
    
    if success:
        print(f"✅ MT5 credentials '{name}' stored securely")
        
        # Test connection
        print("\n🧪 Testing connection (requires MT5 terminal running)...")
        ok, msg = manager.test_credential('mt5', name)
        if ok:
            print(f"✅ {msg}")
        else:
            print(f"⚠️  Test failed: {msg}")
            print("   Ensure MT5 terminal is running and credentials are correct")
        return True
    else:
        print("❌ Failed to store credentials")
        return False


def cmd_list(args):
    """List all stored credentials"""
    manager = get_credential_manager()
    
    print("\n📋 Stored Broker Credentials")
    print("-" * 60)
    
    accounts = manager.list_stored_accounts()
    
    if not accounts:
        print("No credentials stored yet.")
        print("\nUse 'python -m scripts.broker.setup_credentials add <broker>' to add credentials")
        return
    
    # Group by broker type
    by_type = {}
    for bt, name in accounts:
        if bt not in by_type:
            by_type[bt] = []
        by_type[bt].append(name)
    
    for broker_type, names in by_type.items():
        print(f"\n{broker_type.upper()}:")
        for name in names:
            cred = manager.get_credential(broker_type, name)
            if cred:
                demo_status = "🧪 demo" if cred.metadata.get('is_demo', True) else "💰 LIVE"
                account_info = f" (acct: {cred.account_id})" if cred.account_id else ""
                print(f"  • {name}{account_info} - {demo_status}")
    
    print(f"\nTotal: {len(accounts)} credential set(s)")


def cmd_remove(args):
    """Remove stored credentials"""
    manager = get_credential_manager()
    
    broker_type = args.broker
    name = args.name
    
    # Confirm deletion
    confirm = input(f"Are you sure you want to delete {broker_type} '{name}'? [y/N]: ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return
    
    if manager.delete_credential(broker_type, name):
        print(f"✅ Deleted {broker_type} credentials '{name}'")
    else:
        print(f"❌ Failed to delete credentials")


def cmd_test(args):
    """Test broker connection"""
    manager = get_credential_manager()
    
    broker_type = args.broker
    name = args.name
    
    print(f"\n🧪 Testing {broker_type} credentials '{name}'...")
    print("-" * 50)
    
    ok, msg = manager.test_credential(broker_type, name)
    
    if ok:
        print(f"✅ {msg}")
    else:
        print(f"❌ {msg}")


def main():
    setup_environment()
    
    parser = argparse.ArgumentParser(
        description="Manage broker credentials for ApexQuantumICT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.broker.setup_credentials add deriv      # Add Deriv.com API token
  python -m scripts.broker.setup_credentials add mt5       # Add MetaTrader 5 credentials
  python -m scripts.broker.setup_credentials list          # Show all stored credentials
  python -m scripts.broker.setup_credentials test deriv demo  # Test Deriv connection
  python -m scripts.broker.setup_credentials remove mt5 broker1 # Remove MT5 credentials
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add new credentials')
    add_parser.add_argument('broker', choices=['deriv', 'mt5'], help='Broker type')
    
    # List command
    subparsers.add_parser('list', help='List all credentials')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove credentials')
    remove_parser.add_argument('broker', help='Broker type')
    remove_parser.add_argument('name', help='Credential name')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test connection')
    test_parser.add_argument('broker', help='Broker type')
    test_parser.add_argument('name', help='Credential name')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Route to appropriate command
    commands = {
        'add': lambda a: cmd_add_deriv(a) if a.broker == 'deriv' else cmd_add_mt5(a),
        'list': cmd_list,
        'remove': cmd_remove,
        'test': cmd_test,
    }
    
    try:
        commands[args.command](args)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
