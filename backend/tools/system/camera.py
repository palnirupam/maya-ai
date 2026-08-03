"""Reliable Windows Camera photo capture helpers."""
from __future__ import annotations

import os
import time
from pathlib import Path


_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic"}


def _camera_roll_dirs() -> list[Path]:
    """Return the usual Windows Camera Roll locations, in preference order."""
    home = Path.home()
    candidates: list[Path] = []
    if os.name == "nt":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                configured, _ = winreg.QueryValueEx(key, "My Pictures")
            configured_path = Path(os.path.expandvars(str(configured)))
            candidates.append(configured_path / "Camera Roll")
        except (ImportError, OSError):
            pass
    
    # Add more common locations where Windows Camera might save
    candidates.extend([
        home / "Pictures" / "Camera Roll",
        home / "OneDrive" / "Pictures" / "Camera Roll",
        home / "Pictures",  # Some camera apps save directly here
        home / "Desktop",   # Fallback location
        Path("C:/Users/Public/Pictures"),  # Public folder
    ])
    
    result: list[Path] = []
    for path in candidates:
        if path not in result:
            result.append(path)
    return result


def _image_snapshot(paths: list[Path]) -> dict[Path, int]:
    snapshot: dict[Path, int] = {}
    for directory in paths:
        if not directory.is_dir():
            continue
        try:
            for path in directory.iterdir():
                if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
                    snapshot[path] = path.stat().st_mtime_ns
        except OSError:
            continue
    return snapshot


def _newest_changed_image(before: dict[Path, int], paths: list[Path]) -> Path | None:
    after = _image_snapshot(paths)
    changed = [path for path, mtime in after.items() if before.get(path) != mtime]
    if not changed:
        return None
    return max(changed, key=lambda path: after[path])


def _find_camera_window():
    import pygetwindow as gw

    for window in gw.getAllWindows():
        title = (getattr(window, "title", "") or "").strip()
        if title and "camera" in title.casefold():
            return window
    return None


def take_camera_photo(timeout: float = 15.0) -> str:
    """Focus the open Windows Camera app, press its shutter, and verify a saved photo."""
    if os.name != "nt":
        return "ERR: Camera photo capture ekhon sudhu Windows-e supported."

    try:
        import pyautogui
        import pygetwindow as gw

        window = _find_camera_window()
        if window is None:
            return "ERR: Camera app open nei. Age camera open koro."

        if getattr(window, "isMinimized", False):
            window.restore()
        window.activate()

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            active = gw.getActiveWindow()
            active_title = (getattr(active, "title", "") or "").casefold()
            if "camera" in active_title:
                break
            time.sleep(0.05)
        else:
            return "ERR: Camera app focus korte parlam na, tai photo tulini."

        camera_dirs = _camera_roll_dirs()
        before = _image_snapshot(camera_dirs)
        pyautogui.press("space")
        
        # Give success feedback immediately - photo is likely taken
        initial_wait = 2.0
        time.sleep(initial_wait)
        
        # Quick check for immediate save
        saved = _newest_changed_image(before, camera_dirs)
        if saved is not None:
            return f"SUCCESS: Camera photo saved: {saved.resolve()}"

        # Extended wait for slower saves (OneDrive sync, etc)
        deadline = time.monotonic() + max(1.0, timeout - initial_wait)
        while time.monotonic() < deadline:
            saved = _newest_changed_image(before, camera_dirs)
            if saved is not None:
                return f"SUCCESS: Camera photo saved: {saved.resolve()}"
            time.sleep(0.2)

        # Photo likely taken but not found in expected locations
        return (
            "PARTIAL: Shutter press korlam, photo hoyeche but file ta khuje pacchi na. "
            "Camera Roll check koro."
        )
    except Exception as exc:
        return f"ERR: Photo tulte parlam na: {exc}"
