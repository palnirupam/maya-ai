import os
import sys
import tempfile
import httpx
import time
from backend.tools.desktop.advanced.whatsapp_manager import WhatsAppManager

def test_whatsapp_auth():
    print("=== Testing WhatsApp Manager Auth ===")
    
    # 1. Test Key Generation & File Creation
    print("\n1. Initializing WhatsAppManager (Testing Key Generation & icacls)...")
    try:
        manager = WhatsAppManager()
        key = manager.api_key
        print(f"[SUCCESS] Key generated/loaded: {key[:8]}...{key[-4:]}")
    except Exception as e:
        print(f"[FAILED] Error initializing WhatsAppManager: {e}")
        return

    # 2. Test Temp File
    key_file = os.path.join(tempfile.gettempdir(), "maya_wa_key.tmp")
    if os.path.exists(key_file):
        print(f"[SUCCESS] Temp file exists at: {key_file}")
    else:
        print(f"[FAILED] Temp file NOT found at {key_file}")
        return

    # 3. Test Node.js API Auth
    print("\n2. Testing Node.js API with injected key...")
    # Give it a second just in case it just spawned
    time.sleep(2)
    
    headers = {"x-api-key": key}
    try:
        # Test valid key
        resp = httpx.get("http://127.0.0.1:9001/status", headers=headers, timeout=5.0)
        if resp.status_code == 200:
            print(f"[SUCCESS] API accepted the key! Status: {resp.json()}")
        else:
            print(f"[FAILED] API rejected the key! Status code: {resp.status_code}, Response: {resp.text}")
            
        # Test invalid key
        resp_invalid = httpx.get("http://127.0.0.1:9001/status", headers={"x-api-key": "wrong_key"}, timeout=5.0)
        if resp_invalid.status_code in [401, 403]:
            print(f"[SUCCESS] API correctly rejected an invalid key (Status {resp_invalid.status_code})")
        else:
            print(f"[FAILED] API did NOT reject invalid key! Status: {resp_invalid.status_code}")
            
    except Exception as e:
        print(f"[FAILED] Error connecting to Node.js service: {e}")

if __name__ == "__main__":
    test_whatsapp_auth()
