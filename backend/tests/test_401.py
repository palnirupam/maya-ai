from fastapi.testclient import TestClient
import os
os.environ["MAYA_TESTING"] = "1"
from backend.api.main import app

def test_401():
    print("Testing 401 on /settings/status with TestClient...")
    with TestClient(app) as client:
        res = client.get("/settings/status")
        print(f"Status Code: {res.status_code}")
        print(f"Response Body: {res.text}")

if __name__ == "__main__":
    test_401()
