"""Stable, overridable locations for Maya's mutable runtime data."""

import os
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


DATA_DIR = runtime_path("MAYA_DATA_DIR", PROJECT_ROOT / "data")
STATE_DIR = runtime_path("MAYA_STATE_DIR", BACKEND_ROOT / "state")
