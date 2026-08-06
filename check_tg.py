from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences
from backend.database.crypto import crypto_manager

def check_telegram_db():
    db = SessionLocal()
    try:
        keys = ["TELEGRAM_BOT_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_PAIRING_CODE"]
        print("=== Telegram Preferences in DB ===")
        for k in keys:
            pref = db.query(UserPreferences).filter(UserPreferences.key == k).first()
            if not pref:
                print(f"{k}: NOT SET (None)")
            else:
                raw_val = pref.value
                try:
                    dec = crypto_manager.decrypt(raw_val, raise_on_failure=False)
                    print(f"{k}: Raw len={len(raw_val) if raw_val else 0}, Decrypted='{dec}'")
                except Exception as e:
                    print(f"{k}: Decryption ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_telegram_db()
