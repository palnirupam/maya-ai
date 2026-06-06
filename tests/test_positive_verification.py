import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.tools.desktop.advanced.browser_tools import read_background_email

async def main():
    print("--- Testing Email Positive Verification & Folder Discovery ---")
    
    result = await read_background_email(limit=1, unread_only=False)
    if "ERROR" in result:
        print(f"Failed to read emails. Error: {result}")
        return
        
    import re
    uid_match = re.search(r'<EMAIL uid="([^"]+)"', result)
    subject_match = re.search(r'<SUBJECT>(.*?)</SUBJECT>', result, re.DOTALL)
    from_match = re.search(r'<FROM>(.*?)</FROM>', result, re.DOTALL)
    
    if not uid_match:
        print("No emails found or failed to parse UID.")
        return
        
    uid = uid_match.group(1)
    subject = subject_match.group(1).strip()
    from_sender = from_match.group(1).strip()
    
    print(f"Extracted Target Email -> UID: {uid}, Subject: '{subject}', From: '{from_sender}'")
    
    # Let's run the verification part directly to see if it passes!
    from backend.database.connection import SessionLocal
    from backend.database.models import UserPreferences
    from backend.database.crypto import crypto_manager
    import imaplib
    import email
    from email.header import decode_header
    
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
        
        # 1. Pre-execution Verification
        res, msg_data = mail.uid("FETCH", uid.encode("utf-8"), "(RFC822)")
        if res != "OK" or not msg_data or msg_data == [None]:
            print(f"ERROR: Verification failed. Could not fetch email with UID {uid}.")
            return
            
        verified = False
        message_id = "Unknown"
        fetched_subj_str = ""
        fetched_from_str = ""
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                
                message_id = msg.get("Message-ID", "Unknown")
                
                fetched_subj, encoding = decode_header(msg["Subject"])[0] if msg["Subject"] else ("No Subject", None)
                if isinstance(fetched_subj, bytes):
                    fetched_subj = fetched_subj.decode(encoding if encoding else "utf-8", errors="ignore")
                    
                fetched_from, encoding = decode_header(msg.get("From", ""))[0] if msg.get("From") else ("Unknown", None)
                if isinstance(fetched_from, bytes):
                    fetched_from = fetched_from.decode(encoding if encoding else "utf-8", errors="ignore")
                    
                fetched_subj_str = fetched_subj
                fetched_from_str = fetched_from
                
                if subject.strip().lower() in fetched_subj.strip().lower() and from_sender.strip().lower() in fetched_from.strip().lower():
                    verified = True
                break
                
        print(f"\nVerification Results:")
        print(f"Expected Subject: {subject.strip().lower()}")
        print(f"Fetched Subject: {fetched_subj_str.strip().lower()}")
        print(f"Expected From: {from_sender.strip().lower()}")
        print(f"Fetched From: {fetched_from_str.strip().lower()}")
        print(f"Is Verified? {verified}")

        if not verified:
            print("ERROR: Verification failed. The provided Subject or Sender does not match the target email.")
            return
            
        print("\n✅ POSITIVE TEST PASSED: Safeguard successfully verified correct email.")
        
        # Test folder discovery
        status, folders = mail.list()
        trash_folder = "[Gmail]/Trash"  # Fallback
        found = False
        if status == "OK":
            for f in folders:
                folder_name = f.decode("utf-8").split(' "/" ')[-1].strip('"')
                lower_name = folder_name.lower()
                if lower_name in ["trash", "bin", "deleted items", "[gmail]/trash", "[gmail]/bin", "inbox.trash"]:
                    trash_folder = folder_name
                    found = True
                    break
        print(f"Discovered Trash Folder: {trash_folder} (Found: {found})")
        
        # Test COPY command parsing
        print(f"Test COPY command string: COPY {uid} \"{trash_folder}\"")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
