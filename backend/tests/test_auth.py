
from fastapi.testclient import TestClient
from backend.api.main import app
client = TestClient(app)
response = client.get("/api/v1/some-endpoint", headers={"Authorization": "Bearer INVALID"})
print(f"Status: {response.status_code}")
print(f"JSON: {response.json()}")
