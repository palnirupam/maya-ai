import os
from google import genai
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Quick script to list models using google-genai
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    # Try fetching from DB
    try:
        import sys
        sys.path.append("c:\\maya-ai\\backend")
        from database.connection import SessionLocal
        from database.models import UserPreferences
        from database.crypto import crypto_manager
        db = SessionLocal()
        pref = db.query(UserPreferences).filter(UserPreferences.key == "GEMINI_API_KEY").first()
        if pref and pref.value:
            api_key = crypto_manager.decrypt(pref.value)
    except Exception as e:
        print("Could not load from DB:", e)

if not api_key:
    print("No API key found")
    exit(1)

client = genai.Client(api_key=api_key)
for model in client.models.list():
    print(f"Model: {model.name}")
