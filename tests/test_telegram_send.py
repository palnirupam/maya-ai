import sys
import os
import asyncio
import httpx

sys.path.insert(0, "c:\\maya-ai")

from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences
from backend.database.crypto import crypto_manager

def load_config():
    db = SessionLocal()
    try:
        pref_token = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_TOKEN").first()
        token = crypto_manager.decrypt(pref_token.value) if pref_token else None
        return token
    finally:
        db.close()

async def test_send():
    token = load_config()
    print("Token loaded:", token is not None)
    if not token:
        return
        
    chat_id = "5045176959"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": "Hello from diagnostic script! Test message.",
        "parse_mode": "Markdown"
    }
    
    print("Sending request...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10.0)
        print("Status code:", resp.status_code)
        print("Response body:", resp.text)

if __name__ == "__main__":
    asyncio.run(test_send())
