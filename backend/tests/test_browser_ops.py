"""Tests for browser automation operations."""
import pytest
from unittest.mock import patch, MagicMock, call

from backend.tools.unified.handlers.browser_ops import (
    handle_browser,
    get_browser_shortcuts_help,
)


@pytest.fixture
def mock_pyautogui():
    """Mock pyautogui to avoid actual keyboard interactions during tests."""
    with patch('backend.tools.unified.handlers.browser_ops.pyautogui') as mock:
        yield mock


@pytest.fixture
def mock_subprocess():
    """Mock subprocess to avoid launching processes during tests."""
    with patch('backend.tools.unified.handlers.browser_ops.subprocess') as mock:
        yield mock


@pytest.fixture
def mock_time():
    """Mock time.sleep to speed up tests."""
    with patch('backend.tools.unified.handlers.browser_ops.time') as mock:
        yield mock


def test_tab_new(mock_pyautogui):
    """Test opening a new tab."""
    result = handle_browser("tab_new")
    
    assert "OK:" in result
    assert "New tab opened" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "t")


def test_tab_close(mock_pyautogui):
    """Test closing current tab."""
    result = handle_browser("tab_close")
    
    assert "OK:" in result
    assert "Tab closed" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "w")


def test_tab_next(mock_pyautogui):
    """Test switching to next tab."""
    result = handle_browser("tab_next")
    
    assert "OK:" in result
    assert "next tab" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "tab")


def test_tab_prev(mock_pyautogui):
    """Test switching to previous tab."""
    result = handle_browser("tab_prev")
    
    assert "OK:" in result
    assert "previous tab" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "shift", "tab")


def test_tab_reopen(mock_pyautogui):
    """Test reopening last closed tab."""
    result = handle_browser("tab_reopen")
    
    assert "OK:" in result
    assert "Reopened" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "shift", "t")


def test_tab_switch_valid(mock_pyautogui):
    """Test switching to specific tab number."""
    result = handle_browser("tab_switch", val=3)
    
    assert "OK:" in result
    assert "tab 3" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "3")


def test_tab_switch_invalid():
    """Test switching to invalid tab number."""
    result = handle_browser("tab_switch", val=0)
    assert "ERR:" in result
    assert "must be 1-9" in result
    
    result = handle_browser("tab_switch", val=10)
    assert "ERR:" in result


def test_bookmark(mock_pyautogui, mock_time):
    """Test bookmarking current page."""
    result = handle_browser("bookmark")
    
    assert "OK:" in result
    assert "bookmarked" in result.lower()
    
    # Should call hotkey and press enter
    assert mock_pyautogui.hotkey.called
    assert mock_pyautogui.press.called


def test_bookmark_all(mock_pyautogui):
    """Test bookmark all tabs dialog."""
    result = handle_browser("bookmark_all")
    
    assert "OK:" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "shift", "d")


def test_bookmarks_manager(mock_pyautogui):
    """Test opening bookmarks manager."""
    result = handle_browser("bookmarks")
    
    assert "OK:" in result
    assert "bookmarks manager" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "shift", "o")


def test_history(mock_pyautogui):
    """Test opening browser history."""
    result = handle_browser("history")
    
    assert "OK:" in result
    assert "history" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "h")


def test_downloads(mock_pyautogui):
    """Test opening downloads page."""
    result = handle_browser("downloads")
    
    assert "OK:" in result
    assert "downloads" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "j")


def test_find(mock_pyautogui):
    """Test opening find in page."""
    result = handle_browser("find")
    
    assert "OK:" in result
    assert "find" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "f")


def test_print(mock_pyautogui):
    """Test opening print dialog."""
    result = handle_browser("print")
    
    assert "OK:" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "p")


def test_save(mock_pyautogui):
    """Test opening save page dialog."""
    result = handle_browser("save")
    
    assert "OK:" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "s")


def test_zoom_in(mock_pyautogui):
    """Test zoom in."""
    result = handle_browser("zoom_in")
    
    assert "OK:" in result
    assert "Zoomed in" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "plus")


def test_zoom_out(mock_pyautogui):
    """Test zoom out."""
    result = handle_browser("zoom_out")
    
    assert "OK:" in result
    assert "Zoomed out" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "minus")


def test_zoom_reset(mock_pyautogui):
    """Test reset zoom to 100%."""
    result = handle_browser("zoom_reset")
    
    assert "OK:" in result
    assert "100%" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "0")


def test_refresh(mock_pyautogui):
    """Test page refresh."""
    result = handle_browser("refresh")
    
    assert "OK:" in result
    assert "refreshed" in result.lower()
    mock_pyautogui.press.assert_called_once_with("f5")


def test_refresh_hard(mock_pyautogui):
    """Test hard refresh with cache clear."""
    result = handle_browser("refresh_hard")
    
    assert "OK:" in result
    assert "cache" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "f5")


def test_fullscreen(mock_pyautogui):
    """Test toggle fullscreen."""
    result = handle_browser("fullscreen")
    
    assert "OK:" in result
    assert "fullscreen" in result.lower()
    mock_pyautogui.press.assert_called_once_with("f11")


def test_devtools(mock_pyautogui):
    """Test opening developer tools."""
    result = handle_browser("devtools")
    
    assert "OK:" in result
    assert "developer tools" in result.lower()
    mock_pyautogui.press.assert_called_once_with("f12")


def test_address_bar(mock_pyautogui):
    """Test focusing address bar."""
    result = handle_browser("address_bar")
    
    assert "OK:" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "l")


def test_search_with_query(mock_pyautogui, mock_time):
    """Test search with query."""
    result = handle_browser("search", name="test query")
    
    assert "OK:" in result
    assert "Searched" in result
    
    # Should open new tab and type query
    assert mock_pyautogui.hotkey.called
    assert mock_pyautogui.typewrite.called
    assert mock_pyautogui.press.called


def test_search_without_query(mock_pyautogui, mock_time):
    """Test search without query."""
    result = handle_browser("search")
    
    assert "OK:" in result
    assert "New tab opened" in result


def test_back(mock_pyautogui):
    """Test navigate back."""
    result = handle_browser("back")
    
    assert "OK:" in result
    assert "back" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("alt", "left")


def test_forward(mock_pyautogui):
    """Test navigate forward."""
    result = handle_browser("forward")
    
    assert "OK:" in result
    assert "forward" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("alt", "right")


def test_home(mock_pyautogui):
    """Test navigate to home page."""
    result = handle_browser("home")
    
    assert "OK:" in result
    mock_pyautogui.hotkey.assert_called_once_with("alt", "home")


def test_open_url_valid(mock_subprocess):
    """Test opening a URL."""
    result = handle_browser("open_url", name="https://example.com")
    
    assert "OK:" in result
    assert "example.com" in result
    
    # Should call subprocess to open URL
    assert mock_subprocess.Popen.called


def test_open_url_missing():
    """Test opening URL without providing URL."""
    result = handle_browser("open_url")
    
    assert "ERR:" in result
    assert "required" in result.lower()


def test_incognito(mock_pyautogui):
    """Test opening incognito window."""
    result = handle_browser("incognito")
    
    assert "OK:" in result
    assert "incognito" in result.lower() or "private" in result.lower()
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "shift", "n")


def test_new_window(mock_pyautogui):
    """Test opening new browser window."""
    result = handle_browser("new_window")
    
    assert "OK:" in result
    mock_pyautogui.hotkey.assert_called_once_with("ctrl", "n")


def test_close_window(mock_pyautogui):
    """Test closing browser window."""
    result = handle_browser("close_window")
    
    assert "OK:" in result
    mock_pyautogui.hotkey.assert_called_once_with("alt", "f4")


def test_unknown_action():
    """Test unknown browser action."""
    result = handle_browser("unknown_action_xyz")
    
    assert "ERR:" in result
    assert "Unknown" in result


def test_error_handling(mock_pyautogui):
    """Test error handling when pyautogui raises exception."""
    mock_pyautogui.hotkey.side_effect = Exception("Test error")
    
    result = handle_browser("tab_new")
    
    assert "ERR:" in result
    assert "Test error" in result


def test_get_browser_shortcuts_help():
    """Test getting browser shortcuts help text."""
    help_text = get_browser_shortcuts_help()
    
    assert isinstance(help_text, str)
    assert "TABS:" in help_text
    assert "BOOKMARKS:" in help_text
    assert "NAVIGATION:" in help_text
    assert "tab_new" in help_text
    assert "Ctrl+T" in help_text


def test_browser_integration_with_language():
    """Test browser operations with language integration."""
    from backend.brain.language_style import set_latest_conversation_style
    from backend.brain.language_policy_enforcer import enforce_style
    
    # Set language to Banglish
    set_latest_conversation_style("banglish")
    
    with patch('backend.tools.unified.handlers.browser_ops.pyautogui'):
        result = handle_browser("tab_new")
        
        # Result should be in English initially
        assert "OK:" in result
        
        # Can be translated to Banglish
        banglish_result = enforce_style(result, "banglish")
        assert isinstance(banglish_result, str)


def test_browser_ops_pc_router_integration():
    """Test browser operations through pc router."""
    from backend.tools.unified.dispatchers.pc_router import pc
    
    with patch('backend.tools.unified.handlers.browser_ops.pyautogui'):
        # Test that browser actions work through pc router with browser_ prefix
        result = pc("browser_tab_new")
        assert "OK:" in result
        
        result = pc("browser_history")
        assert "OK:" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
