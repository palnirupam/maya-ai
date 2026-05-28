"""
Maya AI — Windows Keyboard Shortcuts & Laptop Controls
Provides Maya with pre-built shortcuts for all common Windows actions.
No need to guess hotkeys — every action is mapped here.
"""
import subprocess
import logging
import time

logger = logging.getLogger(__name__)

# ── Shortcut Action Map ────────────────────────────────────────────────────────
# Maps action names → (keys_tuple, description)
_SHORTCUT_MAP = {
    # Screenshot
    "screenshot":               (("win", "shift", "s"),  "Screenshot snipping tool"),
    "fullscreen_screenshot":    (("printscreen",),        "Full screen screenshot"),

    # System
    "lock":                     (("win", "l"),            "Lock screen"),
    "task_view":                (("win", "tab"),          "Task View (all open windows)"),
    "show_desktop":             (("win", "d"),            "Show/hide desktop"),
    "minimize_all":             (("win", "d"),            "Minimize all windows"),
    "open_settings":            (("win", "i"),            "Open Windows Settings"),
    "open_action_center":       (("win", "a"),            "Open Action Center / Quick Settings"),
    "open_search":              (("win", "s"),            "Open Windows Search"),
    "open_run":                 (("win", "r"),            "Open Run dialog"),
    "open_emoji":               (("win", "."),            "Open Emoji Picker"),
    "open_clipboard_history":   (("win", "v"),            "Open Clipboard History"),
    "open_file_explorer":       (("win", "e"),            "Open File Explorer"),
    "open_task_manager":        (("ctrl", "shift", "esc"), "Open Task Manager"),
    "open_notification":        (("win", "n"),            "Open Notification Center"),
    "open_quick_link":          (("win", "x"),            "Open Quick Link / Power User menu"),

    # Virtual Desktops
    "virtual_desktop_new":      (("win", "ctrl", "d"),       "Create new virtual desktop"),
    "virtual_desktop_close":    (("win", "ctrl", "f4"),      "Close current virtual desktop"),
    "virtual_desktop_next":     (("win", "ctrl", "right"),   "Switch to next virtual desktop"),
    "virtual_desktop_prev":     (("win", "ctrl", "left"),    "Switch to previous virtual desktop"),

    # Window Management
    "snap_left":                (("win", "left"),         "Snap current window to left"),
    "snap_right":               (("win", "right"),        "Snap current window to right"),
    "snap_top":                 (("win", "up"),           "Maximize / snap to top"),
    "snap_bottom":              (("win", "down"),         "Minimize / snap to bottom"),
    "maximize_window":          (("win", "up"),           "Maximize current window"),
    "minimize_window":          (("win", "down"),         "Minimize current window"),
    "close_window":             (("alt", "f4"),           "Close current window"),
    "switch_window":            (("alt", "tab"),          "Switch to next window (Alt+Tab)"),
    "switch_window_back":       (("alt", "shift", "tab"), "Switch to previous window"),
    "switch_same_app":          (("win", "`"),            "Switch between same app windows"),

    # Browser / App Tabs
    "new_tab":                  (("ctrl", "t"),           "Open new tab"),
    "close_tab":                (("ctrl", "w"),           "Close current tab"),
    "reopen_tab":               (("ctrl", "shift", "t"), "Reopen last closed tab"),
    "next_tab":                 (("ctrl", "tab"),         "Switch to next tab"),
    "prev_tab":                 (("ctrl", "shift", "tab"), "Switch to previous tab"),
    "new_window":               (("ctrl", "n"),           "Open new window"),
    "new_incognito":            (("ctrl", "shift", "n"), "Open new incognito/private window"),
    "refresh":                  (("f5",),                 "Refresh page"),
    "hard_refresh":             (("ctrl", "shift", "r"), "Hard refresh (clear cache)"),
    "stop_loading":             (("esc",),                "Stop page loading"),
    "full_screen":              (("f11",),                "Toggle full screen"),
    "zoom_in":                  (("ctrl", "="),           "Zoom in"),
    "zoom_out":                 (("ctrl", "-"),           "Zoom out"),
    "zoom_reset":               (("ctrl", "0"),           "Reset zoom to 100%"),
    "back":                     (("alt", "left"),         "Go back"),
    "forward":                  (("alt", "right"),        "Go forward"),

    # Text Editing
    "select_all":               (("ctrl", "a"),           "Select all"),
    "copy":                     (("ctrl", "c"),           "Copy"),
    "paste":                    (("ctrl", "v"),           "Paste"),
    "cut":                      (("ctrl", "x"),           "Cut"),
    "undo":                     (("ctrl", "z"),           "Undo"),
    "redo":                     (("ctrl", "y"),           "Redo"),
    "find":                     (("ctrl", "f"),           "Find / Search in page or document"),
    "find_replace":             (("ctrl", "h"),           "Find and Replace"),
    "save":                     (("ctrl", "s"),           "Save"),
    "save_as":                  (("ctrl", "shift", "s"), "Save As"),
    "print":                    (("ctrl", "p"),           "Print"),
    "bold":                     (("ctrl", "b"),           "Bold text"),
    "italic":                   (("ctrl", "i"),           "Italic text"),
    "underline":                (("ctrl", "u"),           "Underline text"),
    "go_to_address_bar":        (("ctrl", "l"),           "Go to address bar / URL bar"),
    "go_to_line_start":         (("home",),               "Go to start of line"),
    "go_to_line_end":           (("end",),                "Go to end of line"),
    "go_to_doc_start":          (("ctrl", "home"),        "Go to start of document"),
    "go_to_doc_end":            (("ctrl", "end"),         "Go to end of document"),
    "delete_word":              (("ctrl", "backspace"),   "Delete previous word"),
    "select_word":              (("ctrl", "shift", "right"), "Select next word"),

    # Media
    "play_pause":               (("playpause",),          "Play or pause media"),
    "next_track":               (("nexttrack",),          "Next media track"),
    "prev_track":               (("prevtrack",),          "Previous media track"),
    "mute":                     (("volumemute",),         "Mute/unmute volume"),

    # Accessibility / Magnifier
    "magnifier_on":             (("win", "+"),            "Turn on magnifier / Zoom in"),
    "magnifier_off":            (("win", "esc"),          "Turn off magnifier"),

    # Developer
    "dev_tools":                (("f12",),                "Open browser Developer Tools"),
    "open_console":             (("ctrl", "shift", "j"), "Open browser console"),
    "inspect_element":          (("ctrl", "shift", "i"), "Inspect element"),
}


def perform_shortcut(action: str) -> str:
    """
    Performs a named Windows keyboard shortcut or system action.
    Use this instead of guessing hotkeys — every action is pre-mapped.
    Args:
        action (str): The shortcut action name. Examples:
            'screenshot', 'lock', 'minimize_all', 'show_desktop', 'task_view',
            'snap_left', 'snap_right', 'close_window', 'switch_window',
            'new_tab', 'close_tab', 'reopen_tab', 'refresh', 'hard_refresh',
            'full_screen', 'zoom_in', 'zoom_out', 'zoom_reset',
            'select_all', 'copy', 'paste', 'cut', 'undo', 'redo',
            'find', 'save', 'save_as', 'print', 'bold', 'italic', 'underline',
            'open_settings', 'open_task_manager', 'open_file_explorer',
            'open_run', 'open_search', 'open_emoji', 'open_clipboard_history',
            'virtual_desktop_new', 'virtual_desktop_close', 'virtual_desktop_next', 'virtual_desktop_prev',
            'play_pause', 'next_track', 'prev_track', 'mute',
            'dev_tools', 'sleep' (puts PC to sleep), 'hibernate'
    """
    import pyautogui

    action_lower = action.strip().lower().replace(" ", "_").replace("-", "_")

    # Special non-keyboard actions
    if action_lower in ("sleep", "suspend"):
        try:
            subprocess.run(
                ["powershell", "-Command", "Add-Type -Assembly System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"],
                capture_output=True, timeout=10
            )
            return "SUCCESS: PC is going to sleep."
        except Exception as e:
            return f"ERROR: Could not put PC to sleep. {e}"

    if action_lower == "hibernate":
        try:
            subprocess.run(["shutdown", "/h"], capture_output=True, timeout=10)
            return "SUCCESS: PC is hibernating."
        except Exception as e:
            return f"ERROR: Could not hibernate. {e}"

    if action_lower == "restart":
        try:
            subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True, timeout=10)
            return "SUCCESS: PC will restart in 5 seconds."
        except Exception as e:
            return f"ERROR: Could not restart. {e}"

    if action_lower == "shutdown":
        try:
            subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True, timeout=10)
            return "SUCCESS: PC will shut down in 5 seconds."
        except Exception as e:
            return f"ERROR: Could not shut down. {e}"

    # Look up in shortcut map
    if action_lower not in _SHORTCUT_MAP:
        available = ", ".join(sorted(_SHORTCUT_MAP.keys()))
        return (
            f"ERROR: Unknown action '{action}'. "
            f"Available actions: {available}"
        )

    keys, description = _SHORTCUT_MAP[action_lower]
    try:
        time.sleep(0.15)  # Small delay to let focus settle
        pyautogui.hotkey(*keys)
        return f"SUCCESS: Performed '{description}' ({'+'.join(keys).upper()})."
    except Exception as e:
        logger.error(f"Shortcut '{action}' failed: {e}")
        return f"ERROR: Could not perform '{action}'. {e}"


def control_brightness(direction: str) -> str:
    """
    Controls the laptop screen brightness.
    Args:
        direction (str): Must be 'up' to increase brightness, 'down' to decrease brightness,
                         or a number 0-100 to set exact brightness (e.g. '70').
    """
    direction = direction.strip().lower()

    # Try to set exact value if numeric
    if direction.isdigit():
        level = int(direction)
        level = max(0, min(100, level))
        ps_cmd = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"
        try:
            result = subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return f"SUCCESS: Brightness set to {level}%."
            return f"ERROR: Could not set brightness. {result.stderr.strip()}"
        except Exception as e:
            return f"ERROR: Brightness control failed. {e}"

    # Get current brightness first
    get_cmd = "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
    try:
        result = subprocess.run(
            ["powershell", "-Command", get_cmd],
            capture_output=True, text=True, timeout=10
        )
        current = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 50
    except Exception:
        current = 50

    step = 15  # Change by 15% each time
    if direction == "up":
        new_level = min(100, current + step)
    elif direction == "down":
        new_level = max(0, current - step)
    else:
        return f"ERROR: direction must be 'up', 'down', or a number 0-100. Got: '{direction}'"

    set_cmd = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{new_level})"
    try:
        result = subprocess.run(
            ["powershell", "-Command", set_cmd],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return f"SUCCESS: Brightness changed from {current}% → {new_level}%."
        # Fallback: use Fn key simulation
        import pyautogui
        if direction == "up":
            pyautogui.press("brightnessup")
            return "SUCCESS: Pressed brightness up key."
        else:
            pyautogui.press("brightnessdown")
            return "SUCCESS: Pressed brightness down key."
    except Exception as e:
        return f"ERROR: Brightness control failed. {e}"


def control_display(action: str) -> str:
    """
    Controls multi-monitor display mode on Windows.
    Args:
        action (str): Must be one of:
            'pc_only'    — Show only laptop screen (disconnect external monitor)
            'duplicate'  — Mirror/duplicate to second monitor
            'extend'     — Extend desktop to second monitor (most common)
            'second_only' — Show only on external monitor
    """
    import pyautogui

    action_lower = action.strip().lower().replace(" ", "_")
    mode_map = {
        "pc_only":     "p",
        "duplicate":   "p",
        "extend":      "p",
        "second_only": "p",
        # All use Win+P then navigate
    }

    # Win+P opens display mode picker
    if action_lower not in ("pc_only", "duplicate", "extend", "second_only"):
        return f"ERROR: Unknown display action '{action}'. Use: pc_only, duplicate, extend, second_only."

    try:
        pyautogui.hotkey("win", "p")
        time.sleep(0.8)

        # Navigate with arrow keys:
        # Order in Win+P menu: PC screen only → Duplicate → Extend → Second screen only
        nav_steps = {
            "pc_only":     0,
            "duplicate":   1,
            "extend":      2,
            "second_only": 3,
        }
        steps = nav_steps[action_lower]
        for _ in range(steps):
            pyautogui.press("down")
            time.sleep(0.15)

        pyautogui.press("enter")
        return f"SUCCESS: Display mode set to '{action}'."
    except Exception as e:
        return f"ERROR: Could not change display mode. {e}"


def manage_window(action: str) -> str:
    """
    Manages the currently active window — maximize, minimize, restore, close, or move to a side.
    Args:
        action (str): One of:
            'maximize'  — Make the current window full screen
            'minimize'  — Minimize the current window to taskbar
            'restore'   — Restore the current window to normal size
            'close'     — Close the current window
            'snap_left' — Snap the current window to the left half of the screen
            'snap_right' — Snap the current window to the right half of the screen
    """
    import pyautogui

    action_lower = action.strip().lower()
    action_map = {
        "maximize":   ("win", "up"),
        "minimize":   ("win", "down"),
        "restore":    ("win", "down"),
        "close":      ("alt", "f4"),
        "snap_left":  ("win", "left"),
        "snap_right": ("win", "right"),
    }

    if action_lower not in action_map:
        return f"ERROR: Unknown window action '{action}'. Use: maximize, minimize, restore, close, snap_left, snap_right."

    try:
        time.sleep(0.1)
        pyautogui.hotkey(*action_map[action_lower])
        return f"SUCCESS: Window '{action}' performed."
    except Exception as e:
        return f"ERROR: Could not perform window action '{action}'. {e}"
