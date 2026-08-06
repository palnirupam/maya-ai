import os
import re

files_to_update = [
    "C:/maya-ai/backend/tools/desktop/advanced/browser_tools.py",
    "C:/maya-ai/backend/voice/output/elevenlabs.py",
    "C:/maya-ai/backend/voice/providers/gemini_live_adapter.py",
    "C:/maya-ai/backend/voice/input/transcriber.py",
    "C:/maya-ai/backend/voice/output/tts_router.py"
]

for file_path in files_to_update:
    if not os.path.exists(file_path):
        print(f"Skipping {file_path}, does not exist.")
        continue
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Find crypto_manager.decrypt(x.value) and change to crypto_manager.decrypt(x.value, raise_on_failure=True)
    # Also handle crypto_mod.crypto_manager.decrypt
    new_content = re.sub(
        r'(crypto_manager\.decrypt\([^,]+)\)',
        r'\1, raise_on_failure=True)',
        content
    )
    
    if new_content != content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {file_path}")
    else:
        print(f"No changes made to {file_path}")
