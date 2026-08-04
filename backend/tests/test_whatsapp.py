
from fastapi.testclient import TestClient
from backend.api.main import app
client = TestClient(app)
print(f"/status/whatsapp: {client.get('/status/whatsapp').status_code} {client.get('/status/whatsapp').json()}")
print(f"/whatsapp/consent: {client.get('/whatsapp/consent').status_code} {client.get('/whatsapp/consent').json()}")
