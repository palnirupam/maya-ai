$ErrorActionPreference = "Continue"
Write-Host "=== A1: MAYA_TESTING ==="
echo "MAYA_TESTING: '$env:MAYA_TESTING'"

Write-Host "`n=== A2: Pytest with MAYA_TESTING unset ==="
$env:MAYA_TESTING=""
python -m pytest backend/tests/test_audit_fixes_deep.py -v -k "TestFix1_DPAPI" 2>&1

Write-Host "`n=== A3: crypt32.dll usage ==="
Select-String -Path backend/database/crypto.py -Pattern "crypt32" -Context 3,12 | Out-String -Stream | Select-Object -First 30

Write-Host "`n=== A4: Read .salt manually ==="
python -c "import os; salt_path=os.path.join(os.environ.get('LOCALAPPDATA', ''), 'MayaAI', '.salt'); f=open(salt_path, 'rb'); print(f.read()); f.close()" 2>&1

Write-Host "`n=== B1: crypto_manager.decrypt calls ==="
Get-ChildItem -Path backend -Recurse -Filter *.py | Select-String -Pattern "\.decrypt\(" 2>&1

Write-Host "`n=== B2: TestClient invalid token ==="
python -c "
from fastapi.testclient import TestClient
from backend.api.main import app
client = TestClient(app)
try:
    response = client.get('/api/v1/some-protected-route', headers={'Authorization': 'Bearer INVALID_TOKEN'})
    print(f'Status: {response.status_code}, Response: {response.json()}')
except Exception as e:
    print('Exception:', e)
" 2>&1

Write-Host "`n=== C1: WhatsApp endpoints ==="
python -c "
from fastapi.testclient import TestClient
from backend.api.main import app
client = TestClient(app)
print('/status/whatsapp:', client.get('/status/whatsapp').status_code, client.get('/status/whatsapp').json())
print('/whatsapp/consent:', client.get('/whatsapp/consent').status_code, client.get('/whatsapp/consent').json())
" 2>&1

Write-Host "`n=== C2: Frontend grep ==="
if (Test-Path frontend/src) {
    Get-ChildItem -Path frontend/src -Recurse -Filter *.tsx | Select-String -Pattern "whatsapp" 2>&1
} else {
    Write-Host "No frontend/src directory found."
}

Write-Host "`n=== D1: Skipped tests ==="
Get-ChildItem -Path backend/tests -Recurse -Filter *.py | Select-String -Pattern "pytest.mark.skip" -Context 0,2 2>&1

Write-Host "`n=== E1: reencrypt_wizard triggers ==="
Get-ChildItem -Path backend -Recurse -Filter *.py | Select-String -Pattern "reencrypt_wizard" 2>&1
if (Test-Path frontend/src) {
    Get-ChildItem -Path frontend/src -Recurse -Filter *.tsx | Select-String -Pattern "reencrypt_wizard" 2>&1
}

Write-Host "`n=== F1: Git log ==="
git log -1 --stat 2>&1

Write-Host "`n=== F2: Git diff ==="
git diff HEAD~1 backend/database/crypto.py 2>&1
