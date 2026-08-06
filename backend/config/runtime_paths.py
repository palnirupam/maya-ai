"""Stable, overridable locations for Maya's mutable runtime data."""

import os
import sys
from pathlib import Path



PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"


def runtime_path(env_name: str, default: Path) -> Path:
    """Resolve an optional path override without depending on the process CWD."""
    raw_value = os.getenv(env_name, "").strip()
    path = Path(raw_value).expanduser() if raw_value else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _get_default_data_dir() -> Path:
    # Strict isolation: Use LOCALAPPDATA only in packaged/frozen mode, or if explicitly requested.
    # Dev mode will naturally fall back to PROJECT_ROOT / "data".
    if getattr(sys, "frozen", False) or os.getenv("MAYA_USE_LOCALAPPDATA", "0") == "1":
        if os.name == "nt":
            appdata = os.getenv("LOCALAPPDATA", "").strip()
            if appdata:
                return Path(appdata) / "MayaAI"
    return PROJECT_ROOT / "data"


def _get_default_state_dir() -> Path:
    if getattr(sys, "frozen", False) or os.getenv("MAYA_USE_LOCALAPPDATA", "1") == "1":
        if os.name == "nt":
            appdata = os.getenv("LOCALAPPDATA", "").strip()
            if appdata:
                return Path(appdata) / "MayaAI" / "state"
    return BACKEND_ROOT / "state"


DATA_DIR = runtime_path("MAYA_DATA_DIR", _get_default_data_dir())
STATE_DIR = runtime_path("MAYA_STATE_DIR", _get_default_state_dir())
LOGS_DIR = runtime_path("MAYA_LOGS_DIR", DATA_DIR / "logs")

# Ensure all runtime directories are created recursively on import
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

