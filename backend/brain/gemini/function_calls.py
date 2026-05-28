from ...tools.desktop.mouse import mouse_tools
from ...tools.desktop.keyboard import keyboard_tools
from ...vision.capture.screen_capture import screen_capture

from ...tools.desktop.apps import open_app, close_app, focus_app, list_open_apps
from ...tools.desktop.advanced.browser_tools import open_url, search_youtube, search_google, gmail_action, send_background_email
from ...tools.desktop.advanced.playwright_browser import playwright_navigate, playwright_click, playwright_type, playwright_screenshot, playwright_get_content, playwright_close, playwright_upload_file
from ...tools.desktop.advanced.google_meet_tools import google_meet_join, google_meet_leave
from ...tools.desktop.advanced.google_classroom_tools import classroom_list_assignments, classroom_upload_file
from ...tools.desktop.app_context import get_app_context
from ...tools.desktop.advanced.file_system_tools import create_file, read_file, list_directory, delete_file, search_local_files
from ...tools.desktop.advanced.terminal_tools import execute_powershell, execute_python
from ...tools.desktop.advanced.system_tools import get_active_windows, change_volume, read_clipboard, write_clipboard, get_system_stats, manage_processes, read_on_screen_text, whatsapp_call, whatsapp_send_message, whatsapp_get_pairing_code, whatsapp_send_file, whatsapp_send_multiple_files, pause_media, setup_missing_tool
from ...tools.desktop.advanced.youtube_player import play_youtube_background, stop_youtube_background
from ...tools.desktop.advanced.vision_tools import find_and_click, wait_for_element, read_active_window_title, is_app_open, take_verified_screenshot
from ...tools.desktop.advanced.memory_tools import remember_fact, recall_facts, forget_fact, schedule_reminder, configure_gmail_credentials
from ...tools.desktop.advanced.contacts import save_contact, get_contact_number
from ...tools.desktop.shortcuts import perform_shortcut, control_brightness, control_display, manage_window
from ...tools.web.search import web_search
from ...tools.desktop.advanced.computer_use import background_app_control, vision_guided_action
from ...tools.desktop.advanced.background_reader import get_app_text_content, get_active_window_info

from ...database.connection import SessionLocal
from ...database.models import UserPreferences
from ...database.crypto import crypto_manager
import logging

logger = logging.getLogger(__name__)

# Basic interaction tools
def type_text(text: str) -> str:
    """Type the specified text using the keyboard."""
    return keyboard_tools.type_text(text)

def press_key(key: str) -> str:
    """Press a specific keyboard key (e.g., 'enter', 'win', 'esc')."""
    return keyboard_tools.press_key(key)

def hotkey(key1: str, key2: str = None, key3: str = None) -> str:
    """Execute a keyboard hotkey combination supporting up to 3 keys (e.g., 'ctrl'+'c', 'win'+'shift'+'s', 'ctrl'+'shift'+'t')."""
    if key3:
        return keyboard_tools.hotkey(key1, key2, key3)
    if key2:
        return keyboard_tools.hotkey(key1, key2)
    return keyboard_tools.hotkey(key1)

def click_mouse() -> str:
    """Perform a left mouse click at the current cursor position."""
    return mouse_tools.click()

def double_click_mouse() -> str:
    """Perform a double click at the current cursor position."""
    return mouse_tools.double_click()

def move_mouse_to(x: int, y: int) -> str:
    """Move the mouse cursor to specific X and Y screen coordinates."""
    return mouse_tools.move_to(x, y)

def get_mouse_position() -> str:
    """Get the current X and Y screen coordinates of the mouse cursor."""
    return mouse_tools.get_position()

def look_at_screen() -> str:
    """
    Capture a screenshot of the user's desktop to see what is currently on their screen.
    Returns the image data in base64 format.
    """
    return "SCREENSHOT_TRIGGERED"

def manage_system_state(action: str) -> str:
    """
    Control the state of the AI assistant application itself.
    Args:
        action (str): Must be either 'shutdown' (to completely close and exit the application) or 'sleep' (to put the app in standby mode).
    """
    return f"SYSTEM_STATE_TRIGGERED:{action}"

def change_interaction_mode(mode: str) -> str:
    """
    Switch the runtime mode and capability profile of the AI assistant.
    Args:
        mode (str): Must be 'coding', 'companion', 'professional', or 'friendly'.
    """
    return f"MODE_CHANGE_TRIGGERED:{mode}"

# Mapping of capability keys to the actual Python functions
CAPABILITY_MAP = {
    "PERM_BROWSER": [
        open_url, search_youtube, search_google, gmail_action, send_background_email,
        playwright_navigate, playwright_click, playwright_type,
        playwright_screenshot, playwright_get_content, playwright_close,
        playwright_upload_file, google_meet_join, google_meet_leave,
        classroom_list_assignments, classroom_upload_file,
    ],
    "PERM_FILESYSTEM": [create_file, read_file, list_directory, delete_file, search_local_files],
    "PERM_TERMINAL": [execute_powershell, execute_python],
    "PERM_SYSTEM": [
        open_app, close_app, focus_app, list_open_apps,
        get_active_windows, change_volume, read_clipboard, write_clipboard,
        get_system_stats, manage_processes, read_on_screen_text,
        whatsapp_call, whatsapp_send_message, whatsapp_get_pairing_code,
        whatsapp_send_file, whatsapp_send_multiple_files,
        pause_media, setup_missing_tool,
        find_and_click, wait_for_element, read_active_window_title,
        is_app_open, take_verified_screenshot,
        play_youtube_background, stop_youtube_background,
    ],
    "PERM_WEB_SEARCH": [web_search]
}

def get_maya_tools() -> list:
    """
    Returns a dynamic list of tools based on the user's saved preferences.
    """
    tools = [
        type_text, press_key, hotkey, click_mouse, 
        double_click_mouse, move_mouse_to, get_mouse_position,
        look_at_screen, manage_system_state, change_interaction_mode,
        remember_fact, recall_facts, forget_fact, schedule_reminder, configure_gmail_credentials,
        # App management is always available (no special permission needed)
        open_app, close_app, focus_app, list_open_apps, is_app_open,
        read_active_window_title,
        # Contact Manager
        save_contact, get_contact_number,
        # Shortcuts & Laptop Controls (always available)
        perform_shortcut, control_brightness, control_display, manage_window,
        # App Knowledge base
        get_app_context,
        # Background Computer Use (always available — no mouse, no focus stealing)
        background_app_control, vision_guided_action,
        get_app_text_content, get_active_window_info,
    ]
    
    db = SessionLocal()
    try:
        for perm_key, funcs in CAPABILITY_MAP.items():
            pref = db.query(UserPreferences).filter(UserPreferences.key == perm_key).first()
            if pref and pref.value:
                try:
                    decrypted = crypto_manager.decrypt(pref.value)
                    if decrypted == "true":
                        tools.extend(funcs)
                except Exception as e:
                    logger.error(f"Error decrypting {perm_key}: {e}")
    finally:
        db.close()
        
    # Load external plugins securely
    import os
    import importlib.util
    from pathlib import Path
    try:
        from ...skills.loader import verify_and_load_plugin
        skills_dir = Path("backend/skills")
        if skills_dir.exists() and skills_dir.is_dir():
            for plugin_file in skills_dir.glob("*.py"):
                if plugin_file.name in ["__init__.py", "scanner.py", "loader.py"]:
                    continue
                if verify_and_load_plugin(plugin_file):
                    try:
                        spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        # Extract all callable functions defined in the plugin
                        for attr_name in dir(module):
                            if not attr_name.startswith("_"):
                                attr = getattr(module, attr_name)
                                if callable(attr) and hasattr(attr, "__name__"):
                                    # Ensure it's not an imported function
                                    if getattr(attr, "__module__", None) == plugin_file.stem:
                                        tools.append(attr)
                    except Exception as e:
                        logger.error(f"Error executing plugin {plugin_file.name}: {e}")
    except ImportError:
        pass
        
    # Deduplicate tools by function name to avoid 400 errors from API providers like DeepSeek
    seen_names = set()
    unique_tools = []
    for tool in tools:
        if hasattr(tool, "__name__"):
            name = tool.__name__
            if name not in seen_names:
                seen_names.add(name)
                unique_tools.append(tool)
        else:
            unique_tools.append(tool)
            
    return unique_tools
