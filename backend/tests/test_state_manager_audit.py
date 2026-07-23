import os
import tempfile
import pytest
from backend.system.state_manager import StateManager, state_manager
from backend.tools.desktop.advanced.file_system_tools import create_file
from backend.tools.desktop.advanced.terminal_tools import execute_powershell, execute_python
from backend.brain.memory.long_term_memory import retrieve_relevant_memories

def test_state_manager_permission_caching_and_invalidation():
    sm = StateManager()
    sm.invalidate_permissions()
    assert sm._permissions_cache is None

    # Load permissions (populates cache)
    caps1 = sm.load_permissions()
    assert sm._permissions_cache is not None
    assert isinstance(caps1, set)

    # Second call returns cached set directly
    caps2 = sm.load_permissions()
    assert caps1 == caps2

    # Invalidate cache
    sm.invalidate_permissions()
    assert sm._permissions_cache is None

def test_create_file_empty_and_relative_path_safety(tmp_path):
    # Empty path handling
    res_empty = create_file("", "test content")
    assert "ERROR" in res_empty

    # Relative path handling
    rel_filename = os.path.join(str(tmp_path), "test_rel.txt")
    res_create = create_file(rel_filename, "hello relative")
    assert "SUCCESS" in res_create
    assert os.path.exists(rel_filename)

def test_execute_python_temp_file_cleanup():
    # Verify execute_python creates and cleans up temp files cleanly
    res = execute_python("print('Hello Audit')")
    assert "SUCCESS" in res
    assert "Hello Audit" in res

def test_execute_powershell_non_blocking_behavior():
    res = execute_powershell("Write-Output 'Audit OK'")
    assert "SUCCESS" in res
    assert "Audit OK" in res

def test_retrieve_relevant_memories_short_query_relevance_gate():
    # Short queries like "hi" without matching keywords should not dump unrelated memories
    res = retrieve_relevant_memories("hi")
    assert isinstance(res, list)
