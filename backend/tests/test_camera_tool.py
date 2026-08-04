from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.tools.system import camera
from backend.tools.unified.handlers import system_ops
from backend.brain.agents.agent_defs import AGENT_TOOLS_MAPPING


def test_pc_camera_photo_dispatches_to_camera_tool(monkeypatch):
    monkeypatch.setattr(camera, "take_camera_photo", lambda: "OK: captured")
    assert system_ops.handle_pc("camera_photo") == "OK: captured"


def test_os_executor_cannot_update_canvas():
    assert "update_canvas" not in AGENT_TOOLS_MAPPING["OS_EXECUTOR"]


def test_take_camera_photo_presses_shutter_and_verifies_file(monkeypatch, tmp_path):
    camera_dir = tmp_path / "Camera Roll"
    camera_dir.mkdir()
    saved = camera_dir / "WIN_20260803_103200.jpg"

    window = SimpleNamespace(title="Camera", isMinimized=False, activate=MagicMock())
    active = SimpleNamespace(title="Camera")
    fake_gw = SimpleNamespace(getAllWindows=lambda: [window], getActiveWindow=lambda: active)

    def press(key):
        assert key == "space"
        saved.write_bytes(b"photo")

    monkeypatch.setattr(camera.os, "name", "nt")
    monkeypatch.setattr(camera, "_camera_roll_dirs", lambda: [camera_dir])
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setitem(
        __import__("sys").modules,
        "pyautogui",
        SimpleNamespace(press=press),
    )

    result = camera.take_camera_photo(timeout=0.5)

    window.activate.assert_called_once()
    assert result == f"OK: Photo tule save kore dilam: {saved.resolve()}"


def test_take_camera_photo_does_not_claim_success_without_camera(monkeypatch):
    fake_gw = SimpleNamespace(getAllWindows=lambda: [], getActiveWindow=lambda: None)
    monkeypatch.setattr(camera.os, "name", "nt")
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setitem(__import__("sys").modules, "pyautogui", SimpleNamespace())

    result = camera.take_camera_photo(timeout=0.1)

    assert result.startswith("ERR:")
    assert "Camera app open nei" in result
