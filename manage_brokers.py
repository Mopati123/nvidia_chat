#!/usr/bin/env python3
"""
Broker Account Management Tool

Manage Deriv and MT5 credentials:
  - List stored accounts
  - Test connections
  - Add new accounts
  - Remove accounts

Usage:
  python manage_brokers.py list
  python manage_brokers.py test deriv
  python manage_brokers.py test mt5
  python manage_brokers.py add deriv
  python manage_brokers.py add mt5
  python manage_brokers.py remove <broker> <name>
"""

import sys
import os
import getpass
import argparse
import json
import time
import locale
import uuid
from typing import Optional

sys.path.insert(0, '.')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# #region agent log
try:
    with open("debug-3c812d.log", "a", encoding="utf-8") as _dbg:
        _dbg.write(json.dumps({
            "sessionId": "3c812d",
            "runId": "pre-fix",
            "hypothesisId": "H10",
            "id": f"log_{uuid.uuid4().hex}",
            "location": "manage_brokers.py:module_init",
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

from trading.brokers.credentials import get_credential_manager, BrokerCredential
from trading.brokers.deriv_broker import DerivBroker
from trading.brokers.mt5_broker import MT5Broker


def get_master_password() -> str:
    """Get credential password from env or prompt interactively."""
    password = os.environ.get("APEX_CREDENTIAL_PASSWORD")
    if password:
        return password
    return getpass.getpass("APEX_CREDENTIAL_PASSWORD: ").strip()


def cmd_list():
    """List all stored broker accounts"""
    print("=" * 70)
    print("📋 STORED BROKER ACCOUNTS")
    print("=" * 70)
    
    manager = get_credential_manager(get_master_password())
    accounts = manager.list_stored_accounts()
    
    if not accounts:
        print("\n❌ No accounts stored yet.")
        print("\nAdd accounts with:")
        print("  python manage_brokers.py add deriv")
        print("  python manage_brokers.py add mt5")
        return
    
    # Group by broker type
    from collections import defaultdict
    grouped = defaultdict(list)
    for broker_type, name in accounts:
        grouped[broker_type].append(name)
    
    for broker_type, names in grouped.items():
        print(f"\n🔹 {broker_type.upper()}")
        for name in names:
            cred = manager.get_credential(broker_type, name)
            if cred:
                emoji = "🧪" if cred.is_demo else "💰"
                account_id = cred.account_id if cred.account_id else "N/A"
                print(f"   {emoji} {name}: Account {account_id}")
    
    print(f"\n✅ Total: {len(accounts)} accounts")


def cmd_test_deriv(name: str = "demo"):
    """Test Deriv connection"""
    print("=" * 70)
    print(f"🧪 TESTING DERIV CONNECTION: {name}")
    print("=" * 70)
    
    manager = get_credential_manager(get_master_password())
    cred = manager.get_credential("deriv", name)
    
    if not cred:
        print(f"\n❌ No Deriv account '{name}' found!")
        print(f"\nAdd it with: python manage_brokers.py add deriv")
        return False
    
    token = cred.credentials.get("token", "")
    print(f"\n📡 Connecting to Deriv API...")
    print(f"   Token: ...{token[-4:]}")
    print(f"   Demo: {'Yes' if cred.is_demo else 'No'}")
    
    success, message, info = DerivBroker.test_connection(token)
    
    print(f"\n{message}")
    
    if info and success:
        print(f"\n📊 Account Details:")
        for key, value in info.items():
            print(f"   {key}: {value}")
    
    return success


def cmd_test_mt5(name: str = "default"):
    """Test MT5 connection"""
    print("=" * 70)
    print(f"🧪 TESTING MT5 CONNECTION: {name}")
    print("=" * 70)
    
    manager = get_credential_manager(get_master_password())
    cred = manager.get_credential("mt5", name)
    
    if not cred:
        print(f"\n❌ No MT5 account '{name}' found!")
        print(f"\nAdd it with: python manage_brokers.py add mt5")
        return False
    
    account_id = cred.account_id
    password = cred.credentials.get("password", "")
    server = cred.credentials.get("server", "")
    
    print(f"\n📡 Connecting to MT5...")
    print(f"   Account: {account_id}")
    print(f"   Server: {server}")
    print(f"   Password: {'*' * len(password)}")
    print(f"   Demo: {'Yes' if cred.is_demo else 'No'}")
    print(f"\n⚠️  Make sure MT5 terminal is running!")
    
    success, message, info = MT5Broker.test_connection(
        int(account_id), password, server
    )
    
    print(f"\n{message}")
    
    if info and success:
        print(f"\n📊 Account Details:")
        for key, value in info.items():
            print(f"   {key}: {value}")
    
    return success


def cmd_add_deriv():
    """Add Deriv account interactively"""
    print("=" * 70)
    print("➕ ADD DERIV ACCOUNT")
    print("=" * 70)
    
    print("\n📝 Get your API token from:")
    print("   https://app.deriv.com/account/api-token")
    print("\n⚠️  Create token with 'Trading Information' and 'Admin' scopes")
    
    name = input("\nAccount name (e.g., 'demo', 'live'): ").strip() or "demo"
    token = getpass.getpass("API Token: ").strip()
    is_demo = input("Is this a demo account? [Y/n]: ").strip().lower() != "n"
    
    if not token:
        print("❌ Token required!")
        return False
    
    print(f"\n🔐 Storing credentials...")
    
    manager = get_credential_manager(get_master_password())
    success = manager.store_credential(
        broker_type="deriv",
        name=name,
        credentials={"token": token},
        is_demo=is_demo,
        metadata={"source": "manage_brokers.py"}
    )
    
    if success:
        print(f"✅ Deriv account '{name}' stored successfully!")
        print(f"\nTest it: python manage_brokers.py test deriv {name}")
        return True
    else:
        print("❌ Failed to store credentials")
        return False


def cmd_add_mt5():
    """Add MT5 account interactively"""
    print("=" * 70)
    print("➕ ADD MT5 ACCOUNT")
    print("=" * 70)
    
    print("\n📝 Enter your MT5 account details:")
    
    name = input("\nAccount name (e.g., 'default', 'live'): ").strip() or "default"
    account_id = input("Account Number: ").strip()
    password = getpass.getpass("Password: ").strip()
    server = input("Server (e.g., 'Weltrade', 'MetaQuotes-Demo'): ").strip()
    is_demo = input("Is this a demo account? [Y/n]: ").strip().lower() != "n"
    
    if not all([account_id, password, server]):
        print("❌ All fields required!")
        return False
    
    print(f"\n🔐 Storing credentials...")
    
    manager = get_credential_manager(get_master_password())
    success = manager.store_credential(
        broker_type="mt5",
        name=name,
        credentials={
            "password": password,
            "server": server
        },
        is_demo=is_demo,
        account_id=account_id,
        metadata={"source": "manage_brokers.py"}
    )
    
    if success:
        print(f"✅ MT5 account '{name}' stored successfully!")
        print(f"\nTest it: python manage_brokers.py test mt5 {name}")
        return True
    else:
        print("❌ Failed to store credentials")
        return False


def cmd_remove(broker_type: str, name: str):
    """Remove a stored account"""
    print("=" * 70)
    print(f"🗑️  REMOVE {broker_type.upper()} ACCOUNT: {name}")
    print("=" * 70)
    
    manager = get_credential_manager(get_master_password())
    cred = manager.get_credential(broker_type, name)
    
    if not cred:
        print(f"\n❌ No {broker_type} account '{name}' found!")
        return False
    
    confirm = input(f"\n⚠️  Are you sure you want to remove {broker_type}/{name}? [y/N]: ")
    
    if confirm.strip().lower() != 'y':
        print("❌ Cancelled")
        return False
    
    success = manager.delete_credential(broker_type, name)
    
    if success:
        print(f"✅ {broker_type}/{name} removed successfully!")
        return True
    else:
        print(f"❌ Failed to remove {broker_type}/{name}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Manage Deriv and MT5 broker credentials",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_brokers.py list
  python manage_brokers.py test deriv
  python manage_brokers.py test mt5
  python manage_brokers.py add deriv
  python manage_brokers.py add mt5
  python manage_brokers.py remove deriv demo
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # list
    subparsers.add_parser('list', help='List all stored accounts')
    
    # test
    test_parser = subparsers.add_parser('test', help='Test broker connection')
    test_parser.add_argument('broker', choices=['deriv', 'mt5'], help='Broker type')
    test_parser.add_argument('name', nargs='?', default=None, help='Account name (optional)')
    
    # add
    add_parser = subparsers.add_parser('add', help='Add new account')
    add_parser.add_argument('broker', choices=['deriv', 'mt5'], help='Broker type')
    
    # remove
    remove_parser = subparsers.add_parser('remove', help='Remove account')
    remove_parser.add_argument('broker', help='Broker type')
    remove_parser.add_argument('name', help='Account name')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == 'list':
            cmd_list()
        
        elif args.command == 'test':
            if args.broker == 'deriv':
                name = args.name or 'demo'
                success = cmd_test_deriv(name)
            else:
                name = args.name or 'default'
                success = cmd_test_mt5(name)
            sys.exit(0 if success else 1)
        
        elif args.command == 'add':
            if args.broker == 'deriv':
                cmd_add_deriv()
            else:
                cmd_add_mt5()
        
        elif args.command == 'remove':
            cmd_remove(args.broker, args.name)
    
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
