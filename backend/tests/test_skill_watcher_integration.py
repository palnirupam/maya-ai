"""
Integration test: skill drop → tool list → skill present

Tests the full hot-reload pipeline end-to-end:
  1. Write a dummy skill file to the skills/ directory
  2. Watcher picks it up and loads into SKILLS_REGISTRY
  3. get_maya_tools() returns the skill's tool
  4. Modify the file → registry updates with new version
  5. Delete the file → registry clears the entry
"""

import time
import threading
import sys
import importlib
from pathlib import Path

import pytest

# Patch sys.path so we can import backend modules
import os
os.chdir(Path(__file__).parent.parent.parent)  # root of maya-ai
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.skills.skill_watcher import (
    SKILLS_REGISTRY, _registry_lock,
    start_skill_watcher, stop_skill_watcher,
    get_dynamic_tools,
)

SKILLS_DIR = Path("backend/skills")
TEST_SKILL = SKILLS_DIR / "test_hello_skill.py"
SETTLE_SECONDS = 1.5   # time for watchdog to fire & registry to update


@pytest.fixture(scope="module", autouse=True)
def _skill_watcher():
    """Start the watcher before these tests and stop it after.

    Under pytest the ``__main__`` block below never runs, so without this
    fixture the observer thread is never started (_OBSERVER stays None) and
    every test fails. This mirrors what app startup does in production.
    """
    start_skill_watcher()
    time.sleep(0.5)  # let the observer thread spin up
    try:
        yield
    finally:
        TEST_SKILL.unlink(missing_ok=True)
        (SKILLS_DIR / "test_bad_skill.py").unlink(missing_ok=True)
        stop_skill_watcher()


def _wait_for(condition_fn, timeout=5.0, interval=0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


def test_skill_load():
    """Dropping a new skill file → tool appears in get_dynamic_tools()."""
    TEST_SKILL.write_text(
        '"""Test skill for hot-reload integration test."""\n\n'
        'def hello_maya():\n'
        '    """Say hello from a dynamically loaded skill."""\n'
        '    return "Hello from hot-reload!"\n\n'
        '__maya_tools__ = [hello_maya]\n',
        encoding="utf-8",
    )
    found = _wait_for(lambda: "test_hello_skill" in SKILLS_REGISTRY)
    assert found, "FAIL: skill was not loaded into SKILLS_REGISTRY within timeout"

    tools = get_dynamic_tools()
    names = [fn.__name__ for fn in tools]
    assert "hello_maya" in names, f"FAIL: 'hello_maya' not in tool list. Got: {names}"
    print("[PASS] test_skill_load PASSED")


def test_skill_modify():
    """Modifying an existing skill -> registry updates with new function."""
    # Modify the file
    TEST_SKILL.write_text(
        '"""Test skill v2."""\n\n'
        'def hello_maya_v2():\n'
        '    """Updated tool."""\n'
        '    return "Hello v2!"\n\n'
        '__maya_tools__ = [hello_maya_v2]\n',
        encoding="utf-8",
    )
    # Wait for old tool to be gone and new tool to appear
    found = _wait_for(
        lambda: "hello_maya_v2" in [fn.__name__ for fn in get_dynamic_tools()]
    )
    assert found, "FAIL: modified skill not updated in registry"

    names = [fn.__name__ for fn in get_dynamic_tools()]
    assert "hello_maya" not in names, "FAIL: stale 'hello_maya' still present after modify"
    print("[PASS] test_skill_modify PASSED")


def test_skill_delete():
    """Deleting a skill file -> registry entry removed."""
    TEST_SKILL.unlink(missing_ok=True)
    cleared = _wait_for(lambda: "test_hello_skill" not in SKILLS_REGISTRY)
    assert cleared, "FAIL: deleted skill still in SKILLS_REGISTRY"
    print("[PASS] test_skill_delete PASSED")


def test_syntax_error_does_not_crash_watcher():
    """A file with a syntax error must be skipped, watcher must remain alive."""
    bad_skill = SKILLS_DIR / "test_bad_skill.py"
    bad_skill.write_text("def broken(:\n    pass\n", encoding="utf-8")
    time.sleep(SETTLE_SECONDS)

    from backend.skills.skill_watcher import _OBSERVER
    assert _OBSERVER is not None and _OBSERVER.is_alive(), \
        "FAIL: watcher crashed after loading a bad skill file"

    bad_skill.unlink(missing_ok=True)
    print("[PASS] test_syntax_error_does_not_crash_watcher PASSED")




if __name__ == "__main__":
    print("\n[START] Starting SkillWatcher integration tests...\n")
    start_skill_watcher()
    time.sleep(0.5)  # let observer thread spin up

    try:
        test_skill_load()
        test_skill_modify()
        test_skill_delete()
        test_syntax_error_does_not_crash_watcher()
        print("\n[SUCCESS] All integration tests PASSED!")
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
    finally:
        # Cleanup
        TEST_SKILL.unlink(missing_ok=True)
        (SKILLS_DIR / "test_bad_skill.py").unlink(missing_ok=True)
        stop_skill_watcher()

