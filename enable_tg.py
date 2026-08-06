from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences
from backend.database.crypto import crypto_manager

def enable_telegram_bot():
    db = SessionLocal()
    try:
        pref = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_ENABLED").first()
        encrypted_true = crypto_manager.encrypt("true")
        if pref:
            pref.value = encrypted_true
        else:
            db.add(UserPreferences(key="TELEGRAM_BOT_ENABLED", value=encrypted_true))
        db.commit()
        print("TELEGRAM_BOT_ENABLED set to 'true' in DB successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    enable_telegram_bot()
