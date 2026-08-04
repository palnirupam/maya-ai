import os
import sys
from unittest.mock import MagicMock

# Mock torch and heavy ML libraries before any imports
sys.modules['torch'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['silero'] = MagicMock()

os.environ["MAYA_TESTING"] = "1"
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences
from backend.database.crypto import crypto_manager

client = TestClient(app)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GEMINI_API_PROVIDER", None)
db = SessionLocal()
try:
    # 1. Store a known valid pref
    real_enc = crypto_manager.encrypt("some_key")
    db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").delete()
    db.add(UserPreferences(key="GEMINI_API_KEY", value=real_enc))
    db.commit()

    # 2. Tamper with the raw DB value so it fails decryption
    pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
    pref.value = "baddata"
    db.commit()

    print("Testing /settings/status with corrupted key...")
    resp = client.get("/settings/status")
    print(f"Status code: {resp.status_code}")
    print(f"Response: {resp.text}")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    assert "unreadable" in resp.text
    print("Test passed! 401 returned correctly.")
    
    # 3. Test Telegram Settings
    pref = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_ENABLED").first()
    if pref:
        pref.value = "baddata"
    else:
        db.add(UserPreferences(key="TELEGRAM_BOT_ENABLED", value="baddata"))
    db.commit()
    print("\nTesting /settings/telegram with corrupted settings...")
    resp = client.get("/settings/telegram")
    print(f"Status code: {resp.status_code}")
    print(f"Response: {resp.text}")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    assert "unreadable" in resp.text
    print("Test passed! 401 returned correctly.")
    
finally:
    db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").delete()
    db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_ENABLED").delete()
    db.commit()
    db.close()
