"""Browser automation via keyboard shortcuts - zero external API cost."""
import subprocess
import time
import pyautogui
from pathlib import Path


def handle_browser(action: str, val: int = 0, name: str = "", state: str = "") -> str:
    """Handle browser automation operations using keyboard shortcuts.
    
    Actions:
        tab_new - Open new tab (Ctrl+T)
        tab_close - Close current tab (Ctrl+W)
        tab_next - Switch to next tab (Ctrl+Tab)
        tab_prev - Switch to previous tab (Ctrl+Shift+Tab)
        tab_reopen - Reopen last closed tab (Ctrl+Shift+T)
        tab_switch - Switch to specific tab number (Ctrl+1-8, Ctrl+9 for last)
        
        bookmark - Bookmark current page (Ctrl+D)
        bookmark_all - Bookmark all tabs (Ctrl+Shift+D)
        bookmarks - Open bookmarks manager (Ctrl+Shift+O)
        
        history - Open history (Ctrl+H)
        downloads - Open downloads (Ctrl+J)
        
        find - Open find in page (Ctrl+F)
        print - Print page (Ctrl+P)
        save - Save page (Ctrl+S)
        
        zoom_in - Zoom in (Ctrl++)
        zoom_out - Zoom out (Ctrl+-)
        zoom_reset - Reset zoom (Ctrl+0)
        
        refresh - Refresh page (F5)
        refresh_hard - Hard refresh, clear cache (Ctrl+F5)
        
        fullscreen - Toggle fullscreen (F11)
        devtools - Open developer tools (F12)
        
        address_bar - Focus address bar (Ctrl+L)
        search - Open new tab and focus search
        
        back - Go back (Alt+Left)
        forward - Go forward (Alt+Right)
        home - Go to home page (Alt+Home)
        
        open_url - Open URL in default browser (name = URL)
        
        incognito - Open new incognito/private window (Ctrl+Shift+N)
        new_window - Open new browser window (Ctrl+N)
        close_window - Close browser window (Alt+F4)
        
    Args:
        action: Operation to perform
        val: Numeric parameter (tab number for tab_switch)
        name: String parameter (URL for open_url)
        state: Additional string parameter
    
    Returns:
        Status message with operation result
    """
    try:
        # Tab management
        if action == "tab_new":
            pyautogui.hotkey("ctrl", "t")
            return "OK: New tab opened"
        
        elif action == "tab_close":
            pyautogui.hotkey("ctrl", "w")
            return "OK: Tab closed"
        
        elif action == "tab_next":
            pyautogui.hotkey("ctrl", "tab")
            return "OK: Switched to next tab"
        
        elif action == "tab_prev":
            pyautogui.hotkey("ctrl", "shift", "tab")
            return "OK: Switched to previous tab"
        
        elif action == "tab_reopen":
            pyautogui.hotkey("ctrl", "shift", "t")
            return "OK: Reopened last closed tab"
        
        elif action == "tab_switch":
            if not (1 <= val <= 9):
                return "ERR: Tab number must be 1-9 (9 = last tab)"
            pyautogui.hotkey("ctrl", str(val))
            return f"OK: Switched to tab {val}"
        
        # Bookmarks
        elif action == "bookmark":
            pyautogui.hotkey("ctrl", "d")
            time.sleep(0.3)
            # Auto-confirm bookmark dialog
            pyautogui.press("enter")
            return "OK: Current page bookmarked"
        
        elif action == "bookmark_all":
            pyautogui.hotkey("ctrl", "shift", "d")
            return "OK: Opened bookmark all tabs dialog"
        
        elif action == "bookmarks":
            pyautogui.hotkey("ctrl", "shift", "o")
            return "OK: Opened bookmarks manager"
        
        # History & Downloads
        elif action == "history":
            pyautogui.hotkey("ctrl", "h")
            return "OK: Opened browser history"
        
        elif action == "downloads":
            pyautogui.hotkey("ctrl", "j")
            return "OK: Opened downloads page"
        
        # Page actions
        elif action == "find":
            pyautogui.hotkey("ctrl", "f")
            return "OK: Opened find in page"
        
        elif action == "print":
            pyautogui.hotkey("ctrl", "p")
            return "OK: Opened print dialog"
        
        elif action == "save":
            pyautogui.hotkey("ctrl", "s")
            return "OK: Opened save page dialog"
        
        # Zoom
        elif action == "zoom_in":
            pyautogui.hotkey("ctrl", "plus")
            return "OK: Zoomed in"
        
        elif action == "zoom_out":
            pyautogui.hotkey("ctrl", "minus")
            return "OK: Zoomed out"
        
        elif action == "zoom_reset":
            pyautogui.hotkey("ctrl", "0")
            return "OK: Reset zoom to 100%"
        
        # Refresh
        elif action == "refresh":
            pyautogui.press("f5")
            return "OK: Page refreshed"
        
        elif action == "refresh_hard":
            pyautogui.hotkey("ctrl", "f5")
            return "OK: Hard refresh (cleared cache)"
        
        # View
        elif action == "fullscreen":
            pyautogui.press("f11")
            return "OK: Toggled fullscreen mode"
        
        elif action == "devtools":
            pyautogui.press("f12")
            return "OK: Opened developer tools"
        
        # Navigation
        elif action == "address_bar":
            pyautogui.hotkey("ctrl", "l")
            return "OK: Address bar focused"
        
        elif action == "search":
            pyautogui.hotkey("ctrl", "t")
            time.sleep(0.2)
            if name:
                pyautogui.typewrite(name, interval=0.05)
                pyautogui.press("enter")
                return f"OK: Searched for '{name}'"
            return "OK: New tab opened for search"
        
        elif action == "back":
            pyautogui.hotkey("alt", "left")
            return "OK: Navigated back"
        
        elif action == "forward":
            pyautogui.hotkey("alt", "right")
            return "OK: Navigated forward"
        
        elif action == "home":
            pyautogui.hotkey("alt", "home")
            return "OK: Navigated to home page"
        
        # Open URL
        elif action == "open_url":
            if not name:
                return "ERR: URL required in 'name' parameter"
            
            # Use Windows start command to open in default browser
            subprocess.Popen(["cmd", "/c", "start", "", name], shell=True)
            return f"OK: Opened {name} in default browser"
        
        # Window management
        elif action == "incognito":
            pyautogui.hotkey("ctrl", "shift", "n")
            return "OK: Opened incognito/private window"
        
        elif action == "new_window":
            pyautogui.hotkey("ctrl", "n")
            return "OK: Opened new browser window"
        
        elif action == "close_window":
            pyautogui.hotkey("alt", "f4")
            return "OK: Closed browser window"
        
        return f"ERR: Unknown browser action '{action}'"
    
    except Exception as e:
        return f"ERR: Browser automation failed: {e}"


def get_browser_shortcuts_help() -> str:
    """Return a comprehensive list of available browser shortcuts."""
    return """
Browser Automation Shortcuts:

TABS:
  tab_new         - New tab (Ctrl+T)
  tab_close       - Close tab (Ctrl+W)
  tab_next        - Next tab (Ctrl+Tab)
  tab_prev        - Previous tab (Ctrl+Shift+Tab)
  tab_reopen      - Reopen closed tab (Ctrl+Shift+T)
  tab_switch N    - Switch to tab N (1-9)

BOOKMARKS:
  bookmark        - Bookmark page (Ctrl+D)
  bookmark_all    - Bookmark all tabs (Ctrl+Shift+D)
  bookmarks       - Bookmarks manager (Ctrl+Shift+O)

NAVIGATION:
  back            - Go back (Alt+Left)
  forward         - Go forward (Alt+Right)
  home            - Home page (Alt+Home)
  address_bar     - Focus address bar (Ctrl+L)
  refresh         - Refresh (F5)
  refresh_hard    - Hard refresh (Ctrl+F5)

PAGE ACTIONS:
  find            - Find in page (Ctrl+F)
  print           - Print (Ctrl+P)
  save            - Save page (Ctrl+S)
  zoom_in         - Zoom in (Ctrl++)
  zoom_out        - Zoom out (Ctrl+-)
  zoom_reset      - Reset zoom (Ctrl+0)

HISTORY & DOWNLOADS:
  history         - History (Ctrl+H)
  downloads       - Downloads (Ctrl+J)

WINDOWS:
  new_window      - New window (Ctrl+N)
  incognito       - Incognito window (Ctrl+Shift+N)
  close_window    - Close window (Alt+F4)

VIEW:
  fullscreen      - Fullscreen (F11)
  devtools        - Developer tools (F12)

DIRECT:
  open_url <url>  - Open URL in default browser
  search <query>  - Search in new tab
"""
