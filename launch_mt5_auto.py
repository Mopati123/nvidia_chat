#!/usr/bin/env python3
"""
Auto-launch MT5 Terminal with saved credentials
Automatically logs into your Weltrade demo account
"""
import sys
import os
import subprocess
import time
import json
import locale
import uuid
from pathlib import Path

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
            "hypothesisId": "H12",
            "id": f"log_{uuid.uuid4().hex}",
            "location": "launch_mt5_auto.py:module_init",
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

def find_mt5_terminal():
    """Find MT5 terminal64.exe installation"""
    common_paths = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        r"C:\MetaTrader 5\terminal64.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\MetaTrader 5\terminal64.exe"),
        os.path.expandvars(r"%APPDATA%\MetaTrader 5\terminal64.exe"),
    ]
    
    # Also search in Program Files subdirectories
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        if os.path.exists(base):
            for root, dirs, files in os.walk(base):
                if 'terminal64.exe' in files:
                    return os.path.join(root, 'terminal64.exe')
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    return None

def main():
    print("=" * 60)
    print("🚀 MT5 Auto-Launcher")
    print("=" * 60)
    
    # Load credentials
    try:
        from trading.brokers.credentials import get_credential_manager
        password = os.environ.get("APEX_CREDENTIAL_PASSWORD")
        if not password:
            print("❌ APEX_CREDENTIAL_PASSWORD is not set")
            print("   Set it in your environment before launching MT5")
            sys.exit(1)
        manager = get_credential_manager(password)
        cred = manager.get_credential('mt5', 'default')
        
        if not cred:
            print("❌ MT5 credentials not found!")
            print("   Run: python setup_credentials.py add mt5")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Failed to load credentials: {e}")
        sys.exit(1)
    
    # Extract credentials
    account = cred.account_id
    password = cred.credentials.get('password', '')
    server = cred.credentials.get('server', '')
    is_demo = cred.is_demo
    
    print(f"\n📋 Credentials Loaded:")
    print(f"   Account: {account}")
    print(f"   Server: {server}")
    print(f"   Type: {'🧪 DEMO' if is_demo else '💰 LIVE'}")
    
    # Find MT5
    print("\n🔍 Searching for MT5 installation...")
    mt5_path = find_mt5_terminal()
    
    if not mt5_path:
        print("❌ MT5 terminal64.exe not found!")
        print("\nCommon locations checked:")
        print("   C:\\Program Files\\MetaTrader 5\\")
        print("   C:\\Program Files (x86)\\MetaTrader 5\\")
        print("\nPlease enter the path manually:")
        mt5_path = input("Path to terminal64.exe: ").strip().strip('"')
        
        if not os.path.exists(mt5_path):
            print("❌ File not found!")
            sys.exit(1)
    
    print(f"✅ Found MT5: {mt5_path}")
    
    # Launch MT5 with auto-login
    print(f"\n🔐 Launching MT5 with auto-login...")
    print("   (This may take a few seconds...)")
    
    try:
        # Method 1: Command-line login (may not work on all MT5 builds)
        # cmd = [
        #     mt5_path,
        #     f"/login:{account}",
        #     f"/password:{password}",
        #     f"/server:{server}"
        # ]
        
        # Method 2: Launch and let MT5 handle login via saved account
        # This requires the account to have "Remember password" checked
        cmd = [mt5_path]
        
        # Launch MT5
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE  # New window
        )
        
        print(f"✅ MT5 launched (PID: {process.pid})")
        print("\n⚠️  IMPORTANT:")
        print("   If this is the first login, you may need to:")
        print("   1. Enter password manually in MT5")
        print("   2. Check 'Remember password' and 'Auto-login'")
        print("   3. Future launches will be fully automatic!")
        print("\n📊 MT5 should connect to:")
        print(f"   Server: {server}")
        print(f"   Account: {account}")
        
        print("\n" + "=" * 60)
        print("✨ MT5 is launching! Check the new window.")
        print("=" * 60)
        
        # Verify connection (with retry)
        print("\n🔍 Verifying MT5 connection...")
        print("   (Waiting for MT5 to initialize...)")
        
        time.sleep(5)  # Give MT5 time to start
        
        try:
            from trading.brokers.mt5_broker import MT5Broker
            
            success, message, info = MT5Broker.test_connection(
                int(account), password, server, max_retries=5
            )
            
            if success:
                print(f"\n✅ {message}")
                print("\n📈 Ready for trading!")
            else:
                print(f"\n⚠️  {message}")
                print("\n   If MT5 is still loading, wait a moment and run:")
                print("   python manage_brokers.py test mt5")
                
        except Exception as e:
            print(f"\n⚠️  Could not verify connection: {e}")
            print("   MT5 may still be initializing.")
        
        # Keep script running
        print("\nPress Ctrl+C to close this window...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Closing...")
            
    except Exception as e:
        print(f"❌ Error launching MT5: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
