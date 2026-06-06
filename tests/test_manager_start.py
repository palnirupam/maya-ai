import sys
import os
import time

sys.path.insert(0, "c:\\maya-ai")

from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager

print("Proactively starting WhatsApp manager via Python...")
whatsapp_manager.start()

print("Waiting for startup...")
time.sleep(3)

print("Checking status...")
status = whatsapp_manager.get_status()
print("Final Status:", status)
