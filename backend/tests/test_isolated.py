import os
import sys

# Fake MAYA_TESTING so we use test environment
os.environ["MAYA_TESTING"] = "1"

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import just the settings router
from backend.api.routes.settings import router
from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences

app = FastAPI()
app.include_router(router)

client = TestClient(app)

def test_gap2_status_endpoint():
    db = SessionLocal()
    try:
        pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
        if pref:
            pref.value = "corrupted_invalid_fernet_token"
        else:
            db.add(UserPreferences(key="GEMINI_API_KEY", value="corrupted_invalid_fernet_token"))
        db.commit()
    finally:
        db.close()

    print("\n=== GAP 2 TEST: hitting GET /settings/status ===")
    response = client.get("/settings/status")
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.json()}")


# Also import whatsapp_manager to test it
def test_gap3_whatsapp_consent():
    print("\n=== GAP 3 TEST: WhatsApp Consent Flow ===")
    
    os.environ["MAYA_TESTING"] = "0"
    
    # 1. Clear consent
    db = SessionLocal()
    try:
        pref = db.query(UserPreferences).filter(UserPreferences.key == "WHATSAPP_TOS_ACCEPTED").first()
        if pref:
            db.delete(pref)
            db.commit()
    finally:
        db.close()
    
    from backend.tools.desktop.advanced.whatsapp_manager import WhatsAppManager
    wa = WhatsAppManager()
    
    print("Attempting to start WhatsApp Manager WITHOUT consent...")
    res = wa.start()
    print(f"wa.start() returned: {res}")
    print(f"wa._startup_error: {wa._startup_error}")
    
    print("\nSetting WhatsApp consent to TRUE...")
    wa.set_tos_consent(True)
    
    # Needs to bypass the 9001 check for the test script
    # but let's just see if it passes the TOS check
    print("Attempting to start WhatsApp Manager WITH consent...")
    res2 = wa.start()
    print(f"wa.start() passed TOS check? {'WhatsApp ToS consent required' not in str(wa._startup_error)}")
    print(f"wa._startup_error now: {wa._startup_error}")

if __name__ == "__main__":
    test_gap2_status_endpoint()
    test_gap3_whatsapp_consent()
