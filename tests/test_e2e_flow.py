import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.tools.desktop.advanced.browser_tools import read_background_email, trash_background_email

async def main():
    print("--- 🚀 E2E Simulation: Maya LLM Email Deletion ---")
    
    # Step 1: Simulate LLM calling read_background_email with a bad query
    bad_query = "First email"
    print(f"\n[LLM Action 1] Calling read_background_email(query='{bad_query}')")
    
    read_res = await read_background_email(limit=1, query=bad_query)
    
    if "ERROR" in read_res:
        print(f"❌ TEST FAILED: read_background_email returned an error:\n{read_res}")
        return
        
    print(f"✅ SUCCESS: read_background_email successfully fell back to 'ALL' and fetched emails.")
    
    import re
    uid_match = re.search(r'<EMAIL uid="([^"]+)"', read_res)
    subject_match = re.search(r'<SUBJECT>(.*?)</SUBJECT>', read_res, re.DOTALL)
    from_match = re.search(r'<FROM>(.*?)</FROM>', read_res, re.DOTALL)
    
    if not uid_match:
        print("❌ TEST FAILED: Could not parse UID from read_background_email output.")
        return
        
    uid = uid_match.group(1)
    subject = subject_match.group(1).strip()
    from_sender = from_match.group(1).strip()
    
    print(f"\n[Extracted Data] UID: {uid}, Subject: '{subject[:30]}...', From: '{from_sender}'")
    
    # Step 2: Simulate LLM calling trash_background_email
    print(f"\n[LLM Action 2] Calling trash_background_email(uid='{uid}', subject='...', from_sender='...')")
    
    trash_res = await trash_background_email(uid=uid, subject=subject, from_sender=from_sender)
    
    if "ERROR" in trash_res:
        print(f"❌ TEST FAILED: trash_background_email failed with error:\n{trash_res}")
        return
        
    print(f"✅ SUCCESS: trash_background_email returned:\n{trash_res}")
    
    print("\n🎉 ALL TESTS PASSED E2E!")

if __name__ == "__main__":
    asyncio.run(main())
