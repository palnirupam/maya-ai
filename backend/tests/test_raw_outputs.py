import sys
from unittest.mock import MagicMock
sys.modules['torch'] = MagicMock()
sys.modules['torchaudio'] = MagicMock()
sys.modules['sounddevice'] = MagicMock()

from fastapi.testclient import TestClient
from backend.api.main import app
from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences

client = TestClient(app)

def test_gap2_status_endpoint():
    db = SessionLocal()
    try:
        pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
        if pref:
            pref.value = b"corrupted_invalid_fernet_token"
        else:
            db.add(UserPreferences(key="GEMINI_API_KEY", value=b"corrupted_invalid_fernet_token"))
        db.commit()
    finally:
        db.close()

    print("\n--- GAP 2 TEST ---")
    response = client.get("/settings/status")
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.json()}")

def test_gap3_whatsapp_consent():
    print("\n--- GAP 3 TEST ---")
    
    # 1. Clear consent
    db = SessionLocal()
    try:
        pref = db.query(UserPreferences).filter(UserPreferences.key == "WHATSAPP_TOS_ACCEPTED").first()
        if pref:
            db.delete(pref)
            db.commit()
    finally:
        db.close()
    
    # 2. Attempt to start
    print("Attempting to get status without consent...")
    response_no_consent = client.get("/status/whatsapp")
    print(f"Status Code: {response_no_consent.status_code}")
    print(f"Response Body: {response_no_consent.json()}")
    
    # 3. Post consent
    print("\nPosting consent...")
    response_consent = client.post("/whatsapp/consent", json={"accepted": True})
    print(f"Status Code: {response_consent.status_code}")
    print(f"Response Body: {response_consent.json()}")
    
    # 4. Attempt to start again
    print("\nAttempting to get status WITH consent...")
    response_with_consent = client.get("/status/whatsapp")
    print(f"Status Code: {response_with_consent.status_code}")
    print(f"Response Body: {response_with_consent.json()}")

if __name__ == "__main__":
    test_gap2_status_endpoint()
    test_gap3_whatsapp_consent()
