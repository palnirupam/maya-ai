import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

async def main():
    from backend.database.connection import SessionLocal
    from backend.database.models import UserPreferences
    from backend.database.crypto import crypto_manager
    import imaplib
    
    gmail_user = os.getenv("GMAIL_EMAIL")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    db = SessionLocal()
    email_pref = db.query(UserPreferences).filter(UserPreferences.key == "GMAIL_EMAIL").first()
    pass_pref = db.query(UserPreferences).filter(UserPreferences.key == "GMAIL_APP_PASSWORD").first()
    gmail_user = crypto_manager.decrypt(email_pref.value)
    gmail_password = crypto_manager.decrypt(pass_pref.value)
    db.close()

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(gmail_user, gmail_password)
        mail.select("inbox")
        
        # Check if UIDPLUS is supported
        status, response = mail.capability()
        print("Capabilities:", response)
        
    except Exception as e:
        print(e)

if __name__ == "__main__":
    asyncio.run(main())
