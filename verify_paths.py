import os
import sys

# Force packaged mode simulation
os.environ["MAYA_USE_LOCALAPPDATA"] = "1"

# Import paths after setting the environment variable
from backend.config.runtime_paths import DATA_DIR, STATE_DIR
from backend.database.crypto import SALT_FILE

print("=== Path Verification ===")
print(f"DATA_DIR: {DATA_DIR}")
print(f"STATE_DIR: {STATE_DIR}")
print(f"SALT_FILE: {SALT_FILE}")

# Check if they point to LOCALAPPDATA
local_appdata = os.environ.get("LOCALAPPDATA", "")
if local_appdata and str(DATA_DIR).startswith(local_appdata):
    print("SUCCESS: Paths are correctly using LOCALAPPDATA")
else:
    print("ERROR: Paths are NOT using LOCALAPPDATA")
