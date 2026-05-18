#!/usr/bin/env python3
"""Quick script to add Deriv credentials from environment variables."""
import os
import sys

sys.path.insert(0, ".")

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

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

success = m.store_credential(
    broker_type="deriv",
    name="demo",
    credentials={"token": TOKEN},
    is_demo=True,
    metadata={"source": "quick_setup"},
)

if success:
    print("[OK] Deriv DEMO credentials stored successfully!")

    cred = m.get_credential("deriv", "demo")
    print("\n   Account: demo")
    print(f"   Type: {'DEMO' if cred and cred.is_demo else 'LIVE'}")
    print(f"   Token: {'present' if cred and cred.credentials.get('token') else 'missing'}")
    print("\n[OK] Ready to test connection!")
    print("   Run: python -m scripts.broker.setup_credentials test deriv demo")
    print("   After testing, remove plaintext Deriv secrets from .env")
else:
    print("[ERROR] Failed to store credentials")
    sys.exit(1)
