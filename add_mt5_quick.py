#!/usr/bin/env python3
"""Quick script to add MT5 credentials from environment variables."""
import sys
import os
sys.path.insert(0, '.')

from trading.brokers.credentials import get_credential_manager

ACCOUNT_ID = os.environ.get("MT5_ACCOUNT_ID", "").strip()
PASSWORD = os.environ.get("MT5_PASSWORD", "").strip()
SERVER = os.environ.get("MT5_SERVER", "").strip()
MASTER_PASSWORD = os.environ.get("APEX_CREDENTIAL_PASSWORD", "").strip()

print("[INFO] Storing MT5 credentials...")
print("-" * 50)

if not all([ACCOUNT_ID, PASSWORD, SERVER]):
    print("[ERROR] MT5_ACCOUNT_ID, MT5_PASSWORD, and MT5_SERVER must be set")
    sys.exit(1)
if not MASTER_PASSWORD:
    print("[ERROR] APEX_CREDENTIAL_PASSWORD is not set")
    sys.exit(1)

m = get_credential_manager(MASTER_PASSWORD)

# Store credential
success = m.store_credential(
    broker_type='mt5',
    name='default',
    credentials={
        'password': PASSWORD,
        'server': SERVER
    },
    is_demo=True,
    account_id=ACCOUNT_ID,
    metadata={'source': 'quick_setup'}
)

if success:
    print("[OK] MT5 DEMO credentials stored successfully!")
    
    # Verify
    cred = m.get_credential('mt5', 'default')
    if cred:
        print(f"\n   Account: {cred.account_id}")
        print(f"   Server: {cred.credentials.get('server', 'N/A')}")
        print(f"   Type: {'DEMO' if cred.is_demo else 'LIVE'}")
        print("\n[OK] Ready to test connection!")
        print("   Run: python setup_credentials.py test mt5 default")
else:
    print("[ERROR] Failed to store credentials")
    sys.exit(1)
