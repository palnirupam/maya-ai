import sys
import os
sys.path.insert(0, os.path.abspath("."))
import traceback

print("=== GAP 4 Test: /status/app and /recover endpoints ===")
try:
    from fastapi.testclient import TestClient
    from backend.api.main import app
    from backend.database import crypto
    
    # Simulate an unreadable key state
    crypto.recovery_required = True
    
    client = TestClient(app)
    
    # Test 1: /settings/status/app
    res1 = client.get("/settings/status/app")
    print(f"GET /settings/status/app -> Status: {res1.status_code}")
    print(f"Response: {res1.json()}")
    
    if res1.json().get("recovery_required") is True:
        print("✅ SUCCESS: /status/app correctly reports recovery_required = True")
    else:
        print("❌ ERROR: recovery_required is false or missing")
        
    # Test 2: /settings/recover without key
    res2 = client.post("/settings/recover", json={})
    print(f"POST /settings/recover (empty) -> Status: {res2.status_code}")
    if res2.status_code == 400:
        print("✅ SUCCESS: Rejected empty key")
        
    # Test 3: /settings/recover with invalid key format
    res3 = client.post("/settings/recover", json={"old_key": "invalid_fernet_key"})
    print(f"POST /settings/recover (invalid key) -> Status: {res3.status_code}")
    if res3.status_code == 400 and "Invalid Fernet key" in res3.json()["detail"]:
        print("✅ SUCCESS: Rejected invalid Fernet key")

except Exception as e:
    print(f"Crash during test: {e}")
    traceback.print_exc()
