import sys
sys.path.append(r'c:\maya-ai')
from backend.tools.desktop.advanced.file_system_tools import search_local_files
from backend.tools.desktop.advanced.browser_tools import send_background_email

print("--- STEP 1: SEARCHING FOR README.MD ---")
# Search under c:\maya-ai
search_res = search_local_files("README.md", root_path="c:\\maya-ai")
print(search_res)

# Extract first found path
import re
paths = re.findall(r'- ([a-zA-Z]:[^\n]+)', search_res)
if not paths:
    print("ERROR: No path extracted.")
    sys.exit(1)
    
found_path = paths[0].strip()
print(f"SUCCESSFULLY FOUND PATH: {found_path}")

print("--- STEP 2: EMAILING ATTACHMENT IN BACKGROUND ---")
email_res = send_background_email(
    to_recipient="devnilasarker@gmail.com",
    subject="Maya AI - Walkthrough Report Attachment! 📝",
    body="Hey Nila!\n\nMaya has successfully executed a recursive search on your laptop's hard drive, located the 'walkthrough.md' report, and attached it directly to this email in the background! \n\nNo mouse was moved, and no browser windows opened. Real, raw AI agency at your fingertips. 😎\n\nLove,\nMaya",
    attachment_path=found_path
)
print("EMAIL RESULT:", email_res)
