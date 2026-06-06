import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Ensure the backend module is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.tools.desktop.advanced.browser_tools import read_background_email, trash_background_email

async def main():
    print("--- Testing Email Deletion Negative Verification ---")
    
    # 1. Read latest email
    print("1. Reading latest email...")
    result = await read_background_email(limit=1, unread_only=False)
    
    if "ERROR" in result:
        print(f"Failed to read emails. Error: {result}")
        return
        
    print(f"Read result successfully.")
    
    # Extract UID, Subject, From
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
    
    print(f"\nExtracted Target Email -> UID: {uid}, Subject: '{subject}', From: '{from_sender}'")
    
    # 2. Test Negative Verification (Wrong Subject)
    bad_subject = "HACKER_INJECTED_SUBJECT_DO_NOT_DELETE"
    print(f"\n2. Attempting to trash with wrong subject: '{bad_subject}'")
    trash_res = await trash_background_email(uid=uid, subject=bad_subject, from_sender=from_sender)
    
    print(f"Result:\n{trash_res}")
    
    if "Verification failed" in trash_res and "BLOCKED" in trash_res:
        print("\n✅ NEGATIVE TEST PASSED: Safeguard successfully blocked deletion of hallucinated email.")
    else:
        print("\n❌ NEGATIVE TEST FAILED: Safeguard did not block the action appropriately.")

if __name__ == "__main__":
    asyncio.run(main())
