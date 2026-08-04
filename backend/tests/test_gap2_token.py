import sys
import os
import traceback

sys.path.insert(0, os.path.abspath("."))

print("=== GAP 2 Test: Settings endpoint with Corrupted Token ===")
try:
    from fastapi.testclient import TestClient
    from backend.api.main import app
    from backend.database.connection import SessionLocal
    from backend.database.models import UserPreferences
    from backend.database import crypto
    
    # 1. Start with fresh DB and set a corrupted GEMINI_API_KEY
    db = SessionLocal()
    pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
    
    # Corrupted token structure
    corrupted_token = b"gAAAAAB_Corrupted_Token_Here_DataDataData"
    
    if not pref:
        pref = UserPreferences(key="GEMINI_API_KEY", value=corrupted_token)
        db.add(pref)
    else:
        pref.value = corrupted_token
        
    db.commit()
    db.close()
    
    # 2. Use TestClient to hit /settings/status
    client = TestClient(app)
    print("Hitting GET /settings/status ...")
    res = client.get("/settings/status")
    
    print(f"Status Code: {res.status_code}")
    print(f"Response Body: {res.json()}")
    
    if res.status_code == 401:
        print("✅ SUCCESS: Properly rejected corrupted token with 401")
    else:
        print("❌ ERROR: Did not reject corrupted token")

except Exception as e:
    print(f"Crash during test: {e}")
    traceback.print_exc()
