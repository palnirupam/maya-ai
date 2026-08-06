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
        continue
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Fix the corrupted strip(, raise_on_failure=True)
    content = content.replace(").strip(, raise_on_failure=True)", ", raise_on_failure=True).strip()")
    content = content.replace(").lower(, raise_on_failure=True)", ", raise_on_failure=True).lower()")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Fixed {file_path}")
