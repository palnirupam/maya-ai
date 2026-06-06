import httpx
import traceback
try:
    resp = httpx.get("http://127.0.0.1:8000/", timeout=10.0)
    print("Response status:", resp.status_code)
    print("Response json:", resp.json())
except Exception as e:
    print("Request failed:")
    traceback.print_exc()
