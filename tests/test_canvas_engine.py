import json
import os
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.system.canvas import write_canvas_state, validate_canvas_path, CANVAS_DIR, MAX_CANVAS_SIZE
from backend.api.main import app

client = TestClient(app)

def setup_module(module):
    # Ensure CANVAS_DIR exists
    os.makedirs(CANVAS_DIR, exist_ok=True)

def test_validate_canvas_path():
    # Valid path
    path = validate_canvas_path("test-session", "index.html")
    assert path.endswith("index.html")
    assert "test-session" in path
    
    # Path traversal attempt
    with pytest.raises(ValueError, match="Path traversal detected"):
        validate_canvas_path("test-session", "../other-session/index.html")

    with pytest.raises(ValueError, match="Path traversal detected"):
        validate_canvas_path("test-session", "../../etc/passwd")

def test_write_canvas_state_limits():
    session_id = "test-limits-session"
    
    # 1. Test normal write and injections
    html = "<html><head></head><body><h1>Hello World</h1></body></html>"
    css = "h1 { color: red; }"
    js = "console.log('hi');"
    
    written_path = write_canvas_state(session_id, html, css, js)
    assert os.path.exists(written_path)
    
    with open(written_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "h1 { color: red; }" in content
    assert "console.log('hi');" in content
    assert "window.Maya = {" in content
    assert "triggerAgent" in content
    
    # 2. Test payload size limit (> 1MB)
    huge_html = "A" * (MAX_CANVAS_SIZE + 100)
    with pytest.raises(ValueError, match="Canvas size limit exceeded"):
        write_canvas_state(session_id, huge_html)
        
    # 3. Clean up
    session_dir = os.path.dirname(written_path)
    if os.path.exists(session_dir):
        shutil.rmtree(session_dir)

def test_canvas_file_serving_and_csp():
    session_id = "test-serving-session"
    html = "<html><head></head><body>Served content</body></html>"
    
    # Write some state
    written_path = write_canvas_state(session_id, html)
    
    try:
        # Request the file via FastAPI test client
        response = client.get(f"/canvas/{session_id}/index.html")
        assert response.status_code == 200
        assert "Served content" in response.text
        
        # Verify Content-Security-Policy header
        csp = response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "connect-src 'none'" in csp
        assert "frame-ancestors 'self'" in csp
        assert "http://localhost:1420" in csp
        assert "http://tauri.localhost" in csp
        assert "default-src 'self' 'unsafe-inline' 'unsafe-eval'" in csp
        
        # Verify other security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert "X-Frame-Options" not in response.headers
        
        # Non-existent file
        response_404 = client.get(f"/canvas/{session_id}/non_existent.html")
        assert response_404.status_code == 404
        
    finally:
        # Clean up
        session_dir = os.path.dirname(written_path)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)


def test_tauri_parent_csp_allows_the_local_canvas_frame():
    config_path = Path(__file__).parents[1] / "frontend" / "src-tauri" / "tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    csp = config["app"]["security"]["csp"]

    assert "frame-src http://127.0.0.1:8000" in csp


def test_local_api_rejects_untrusted_browser_origin_and_hides_debug_routes():
    response = client.get("/", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403

    assert not any(
        getattr(route, "path", None) == "/canvas/debug/trigger"
        and "POST" in (getattr(route, "methods", set()) or set())
        for route in app.routes
    )
    assert client.post("/canvas/debug/trigger").status_code in {404, 405}
    assert client.get("/docs").status_code == 404


def test_websocket_rejects_untrusted_origin_before_accepting():
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/ws",
            headers={"Origin": "https://evil.example"},
        ):
            pass

    assert exc_info.value.code == 1008

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
