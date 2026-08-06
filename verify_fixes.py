import os
import subprocess
import glob
from pathlib import Path

def run_cmd(cmd, env=None, cwd=None):
    print(f"\n$ {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, env=env, cwd=cwd, text=True, capture_output=True)
        if result.stdout:
            print(result.stdout.strip()[:1500])
        if result.stderr:
            print(result.stderr.strip()[:1500])
    except Exception as e:
        print(f"Error: {e}")

print("=== A. FIX 1 (DPAPI) ===")
print("A1. Check MAYA_TESTING env var:")
run_cmd("echo %MAYA_TESTING%")

print("\nA2. Run pytest for TestFix1_DPAPI with MAYA_TESTING unset:")
env = os.environ.copy()
env.pop("MAYA_TESTING", None)
run_cmd("python -m pytest backend/tests/test_audit_fixes_deep.py -k TestFix1_DPAPI -v", env=env)

print("\nA3. Code snippet showing crypt32.dll usage:")
run_cmd('powershell -Command "Select-String -Path backend/database/crypto.py -Pattern crypt32.dll -Context 2,5"')

print("\nA4. Manual script to read .salt:")
# Ensure the key is generated first
run_cmd('python -c "from backend.database.crypto import crypto_manager; crypto_manager.encrypt(\'test\')"')
run_cmd('python -c "import os; p=os.path.join(os.environ.get(\'LOCALAPPDATA\',\'\'), \'MayaAI\', \'.salt\'); f=open(p, \'rb\'); print(f.read()[:50]); f.close()"')

print("\n=== B. FIX 4 (Decrypt Failures) ===")
print("B1. Grep crypto_manager.decrypt in backend/ (excluding .venv):")
run_cmd('powershell -Command "Get-ChildItem -Path backend -Recurse -File | Where-Object {$_.FullName -notmatch \'\\\\.venv\\\\\'} | Select-String -Pattern crypto_manager.decrypt | Select-Object -First 10"')

print("\nB2. TestClient invalid token on protected endpoint:")
testclient_auth = """
from fastapi.testclient import TestClient
from backend.api.main import app
client = TestClient(app)
response = client.get("/api/v1/some-endpoint", headers={"Authorization": "Bearer INVALID"})
print(f"Status: {response.status_code}")
print(f"JSON: {response.json()}")
"""
with open("test_auth.py", "w") as f:
    f.write(testclient_auth)
run_cmd("python test_auth.py")

print("\n=== C. FIX 5 & 7 (WhatsApp HTTP API) ===")
print("C1. TestClient WhatsApp endpoints:")
testclient_whatsapp = """
from fastapi.testclient import TestClient
from backend.api.main import app
client = TestClient(app)
print(f"/status/whatsapp: {client.get('/status/whatsapp').status_code} {client.get('/status/whatsapp').json()}")
print(f"/whatsapp/consent: {client.get('/whatsapp/consent').status_code} {client.get('/whatsapp/consent').json()}")
"""
with open("test_whatsapp.py", "w") as f:
    f.write(testclient_whatsapp)
run_cmd("python test_whatsapp.py")

print("\nC2. Frontend grep for whatsapp endpoints:")
run_cmd('powershell -Command "if (Test-Path frontend/src) { Get-ChildItem -Path frontend/src -Recurse -File | Select-String -Pattern \'/status/whatsapp\' } else { Write-Host \'Frontend missing\' }"')

print("\n=== D. Skip Tests ===")
print("D1. Grep pytest.mark.skip in backend/tests:")
run_cmd('powershell -Command "Get-ChildItem -Path backend/tests -Recurse -File | Select-String -Pattern pytest.mark.skip -Context 0,2"')

print("\n=== E. FIX 2 (Recovery UI) ===")
print("E1. Grep reencrypt_wizard in project:")
run_cmd('powershell -Command "Get-ChildItem -Path . -Recurse -File | Where-Object {$_.FullName -notmatch \'\\\\.venv\\\\\' -and $_.FullName -notmatch \'\\\\node_modules\\\\\' -and $_.FullName -notmatch \'\\\\.git\\\\\'} | Select-String -Pattern reencrypt_wizard | Select-Object -First 10"')

print("\n=== F. Git Verification ===")
print("F1. Git log:")
run_cmd("git log -1 --stat")
print("\nF2. Git diff:")
run_cmd("git diff HEAD~1 backend/database/crypto.py")
