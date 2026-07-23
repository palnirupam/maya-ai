"""Global pytest bootstrap that keeps all mutable state out of user data."""

import os
import tempfile
import uuid
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent
_TEST_ROOT = _PROJECT_ROOT / ".test-runtime"
_TEMP_DIR = _TEST_ROOT / "tmp" / f"run-{uuid.uuid4().hex}"

for directory in (_TEST_ROOT, _TEMP_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# Set these before pytest imports any backend module with import-time singletons.
os.environ["MAYA_TESTING"] = "1"
os.environ["MAYA_ENABLE_DEBUG_ROUTES"] = "0"
os.environ["MAYA_DATA_DIR"] = str(_TEST_ROOT / "data")
os.environ["MAYA_STATE_DIR"] = str(_TEST_ROOT / "state")
os.environ["MAYA_LOG_DIR"] = str(_TEST_ROOT / "logs")
os.environ["MAYA_OUTPUT_DIR"] = str(_TEST_ROOT / "output")
os.environ["TEMP"] = str(_TEMP_DIR)
os.environ["TMP"] = str(_TEMP_DIR)

# tempfile may have cached the user-profile temp directory before conftest loaded.
tempfile.tempdir = str(_TEMP_DIR)
