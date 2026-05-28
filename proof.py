import os

files = [
    'backend/utils/audit_logger.py',
    'backend/scripts/reencrypt_wizard.py',
    'backend/database/crypto.py',
    'backend/database/recovery.py',
    'backend/skills/scanner.py',
    'backend/skills/loader.py',
    'backend/brain/security_filter.py',
    'backend/brain/orchestrator.py',
    'backend/brain/gemini/function_calls.py'
]

with open('claude_proof.txt', 'w', encoding='utf-8') as out:
    for f in files:
        if os.path.exists(f):
            out.write(f'--- {f} ---\n')
            with open(f, 'r', encoding='utf-8') as file_in:
                out.write(file_in.read())
            out.write('\n\n')
