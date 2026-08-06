from fastapi.testclient import TestClient
from backend.api.main import app
import subprocess

client = TestClient(app)

print("=== B2: TestClient invalid token ===")
try:
    response = client.get('/api/v1/health', headers={'Authorization': 'Bearer INVALID'})
    print(f"Status: {response.status_code}")
    print(f"JSON: {response.json()}")
except Exception as e:
    print(f"Exception: {e}")

print("=== C1: WhatsApp endpoints ===")
try:
    print(f"/status/whatsapp: {client.get('/status/whatsapp').status_code} {client.get('/status/whatsapp').text}")
    print(f"/whatsapp/consent: {client.get('/whatsapp/consent').status_code} {client.get('/whatsapp/consent').text}")
except Exception as e:
    print(f"Exception: {e}")

print("=== F1: Git Log ===")
print(subprocess.run(["git", "log", "-1", "--stat"], capture_output=True, text=True).stdout)

print("=== F2: Git Diff ===")
print(subprocess.run(["git", "diff", "HEAD~1", "backend/database/crypto.py"], capture_output=True, text=True).stdout)
