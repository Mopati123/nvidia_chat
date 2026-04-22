#!/usr/bin/env python3
"""Quick script to add Deriv credentials from environment variables."""
import sys
import os
sys.path.insert(0, '.')

from trading.brokers.credentials import get_credential_manager

TOKEN = os.environ.get("DERIV_API_TOKEN", "").strip()
MASTER_PASSWORD = os.environ.get("APEX_CREDENTIAL_PASSWORD", "").strip()

print("[INFO] Storing Deriv credentials...")
print("-" * 50)

if not TOKEN:
    print("[ERROR] DERIV_API_TOKEN is not set")
    sys.exit(1)
if not MASTER_PASSWORD:
    print("[ERROR] APEX_CREDENTIAL_PASSWORD is not set")
    sys.exit(1)

m = get_credential_manager(MASTER_PASSWORD)

# Store credential
success = m.store_credential(
    broker_type='deriv',
    name='demo',
    credentials={'token': TOKEN},
    is_demo=True,
    metadata={'source': 'quick_setup'}
)

if success:
    print("[OK] Deriv DEMO credentials stored successfully!")
    
    # Verify
    cred = m.get_credential('deriv', 'demo')
    print(f"\n   Account: {cred.name}")
    print(f"   Type: {'🧪 DEMO' if cred.is_demo else '💰 LIVE'}")
    print(f"   Token: ***{cred.credentials['token'][-4:]}")
    print("\n[OK] Ready to test connection!")
    print("   Run: python setup_credentials.py test deriv demo")
else:
    print("[ERROR] Failed to store credentials")
    sys.exit(1)
