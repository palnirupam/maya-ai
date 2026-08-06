import os
import re

def fix_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        if "long_term_memory.py" in filepath or "crypto_doctor.py" in filepath or "crypto_selfheal.py" in filepath or "crypto_reseal_gemini.py" in filepath or "test_memory.py" in filepath:
            return

        new_content = re.sub(r'crypto_manager\.decrypt\(([^,)]+)\)', r'crypto_manager.decrypt(\1, raise_on_failure=True)', content)
        new_content = re.sub(r'crypto_mod\.crypto_manager\.decrypt\(([^,)]+)\)', r'crypto_mod.crypto_manager.decrypt(\1, raise_on_failure=True)', new_content)

        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Fixed {filepath}")
    except Exception as e:
        print(f"Error on {filepath}: {e}")

for root, dirs, files in os.walk('C:/maya-ai/backend'):
    if "__pycache__" in root:
        continue
    for file in files:
        if file.endswith('.py'):
            fix_file(os.path.join(root, file))

print("Done fixing crypto calls.")
