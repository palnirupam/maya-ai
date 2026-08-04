import os
import sys
import tempfile
import importlib
from pathlib import Path

print("=== GAP 1: Testing Salt File Path ===")

# Test 1: Dev Mode
os.environ["MAYA_USE_LOCALAPPDATA"] = "0"
os.environ["MAYA_TESTING"] = "1"  # to avoid real dpapi errors in CI

import backend.config.runtime_paths
import backend.database.crypto

print("\n--- DEV MODE ---")
print(f"SALT_FILE path: {backend.database.crypto.SALT_FILE}")
expected_dev = backend.config.runtime_paths.PROJECT_ROOT / "data" / ".salt"
print(f"Expected:       {expected_dev}")
assert backend.database.crypto.SALT_FILE == expected_dev, "Dev mode path mismatch!"
print("Dev mode path verified successfully.")

# Test 2: Frozen Mode
print("\n--- FROZEN (PACKAGED) MODE ---")
with tempfile.TemporaryDirectory() as temp_dir:
    os.environ["LOCALAPPDATA"] = temp_dir
    sys.frozen = True
    
    # Reload modules to pick up new sys.frozen and LOCALAPPDATA
    importlib.reload(backend.config.runtime_paths)
    importlib.reload(backend.database.crypto)
    
    salt_file = backend.database.crypto.SALT_FILE
    print(f"SALT_FILE path: {salt_file}")
    expected_frozen = Path(temp_dir) / "MayaAI" / ".salt"
    print(f"Expected:       {expected_frozen}")
    assert salt_file == expected_frozen, "Frozen mode path mismatch!"
    
    # Simulate writing the salt file
    print("\nSimulating salt file creation...")
    backend.database.crypto.crypto_manager.encrypt("test_payload")
    
    if salt_file.exists():
        print(f"SUCCESS: Salt file physically created at {salt_file}")
        print(f"Raw contents (first 20 bytes): {salt_file.read_bytes()[:20]}")
    else:
        print("FAILED: Salt file was not created!")
        sys.exit(1)

print("\nAll GAP 1 tests passed!")
