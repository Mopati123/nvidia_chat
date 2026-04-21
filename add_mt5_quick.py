#!/usr/bin/env python3
"""Quick script to add MT5 credentials"""
import sys
sys.path.insert(0, '.')

from trading.brokers.credentials import get_credential_manager

# MT5 credentials
ACCOUNT_ID = "19894320"
PASSWORD = "3g)Q7$tX"
SERVER = "Weltrade"

print("🔐 Storing MT5 credentials...")
print("-" * 50)

# Get manager with default password
m = get_credential_manager('apex_secure_2024')

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
    print("✅ MT5 DEMO credentials stored successfully!")
    
    # Verify
    cred = m.get_credential('mt5', 'default')
    if cred:
        print(f"\n   Account: {cred.account_id}")
        print(f"   Server: {cred.credentials.get('server', 'N/A')}")
        print(f"   Type: {'🧪 DEMO' if cred.is_demo else '💰 LIVE'}")
        print("\n🎉 Ready to test connection!")
        print("   Run: python setup_credentials.py test mt5 default")
else:
    print("❌ Failed to store credentials")
    sys.exit(1)
