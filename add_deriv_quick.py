#!/usr/bin/env python3
"""Quick script to add Deriv credentials"""
import sys
sys.path.insert(0, '.')

from trading.brokers.credentials import get_credential_manager

# Token from user
TOKEN = "kmphSqW2CMJ3wli"

print("🔐 Storing Deriv credentials...")
print("-" * 50)

# Get manager with default password
m = get_credential_manager('apex_secure_2024')

# Store credential
success = m.store_credential(
    broker_type='deriv',
    name='demo',
    credentials={'token': TOKEN},
    is_demo=True,
    metadata={'source': 'quick_setup'}
)

if success:
    print("✅ Deriv DEMO credentials stored successfully!")
    
    # Verify
    cred = m.get_credential('deriv', 'demo')
    print(f"\n   Account: {cred.name}")
    print(f"   Type: {'🧪 DEMO' if cred.is_demo else '💰 LIVE'}")
    print(f"   Token: ***{cred.credentials['token'][-4:]}")
    print("\n🎉 Ready to test connection!")
    print("   Run: python setup_credentials.py test deriv demo")
else:
    print("❌ Failed to store credentials")
    sys.exit(1)
