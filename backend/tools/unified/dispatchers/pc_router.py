"""LLM-facing pc (system control) router — single tool covers 20+ actions."""
from ..handlers.system_ops import handle_pc
from ..handlers.wifi_bt_ops import handle_wifi, handle_bt
from backend.brain.language_style import get_latest_conversation_style
from backend.brain.language_policy_enforcer import enforce_style


def pc(action: str = "", val: int = 0, name: str = "", state: str = "", cmd: str = "", ssid: str = "", password: str = "") -> str:
    """
    Universal system control router (zero external API cost - pure Windows/Python).

    Actions (action parameter):
      volume val          — Set volume 0-100
      brightness val      — Set brightness 0-100
      lock                — Lock PC (Win+L)
      mute                — Toggle mute
      screenshot          — Capture screenshot (returns base64)
      camera_photo        — Take and verify a photo in the open Windows Camera app
      sleep               — Sleep mode
      shutdown            — Shutdown in 5s
      restart             — Restart in 5s
      hibernate           — Hibernate
      clipboard_read      — Read clipboard text
      clipboard_write     — Write text to clipboard (pass text in name)
      process_list [cmd]  — List top processes (cmd=cpu|mem)
      process_kill val    — Kill by PID (val) or name (name parameter)
      battery             — Battery status
      network             — Network/IP info
      stats               — CPU/RAM/Disk usage
      active_windows      — List visible windows
      
      # Multiple Monitor Configuration
      display_list        — List all connected displays
      display_settings    — Open Windows Display Settings
      display_orientation val — Rotate display (0=landscape, 1=portrait, 2=flipped landscape, 3=flipped portrait)
      display_extend name — Set display mode: 'pc_only', 'duplicate', 'extend', 'second_only'
      
      # Keyboard Shortcut Customization
      hotkey_remap name state — Remap key (name=source, state=target, e.g., CapsLock→Ctrl)
      hotkey_list         — List all custom hotkey remappings
      hotkey_reset        — Clear all hotkey remappings
      
      # System Theme/Appearance
      theme_dark val      — Dark mode (val=1) or Light mode (val=0)
      theme_accent name   — Set accent color (name=hex color like 'FF0000')
      theme_wallpaper name — Set wallpaper (name=image file path)
      theme_transparency val — Enable (val=1) or disable (val=0) transparency effects
      
      # Notification Center
      notification_open   — Open Notification Center
      notification_clear  — Clear all notifications
      notification_list   — List recent notifications
      notification_focus  — Open Focus Assist (Do Not Disturb) settings
      
      # Wallpaper Feedback & Management
      wallpaper_dislike name — User dislikes current wallpaper, try alternative (name=theme)
      wallpaper_restore   — Restore previous wallpaper from history
      wallpaper_suggest name — Suggest alternative themes (name=current_theme)
      wallpaper_like      — Mark current wallpaper as liked
      
      # Browser Automation (keyboard shortcuts, zero API cost)
      browser_tab_new     — Open new browser tab
      browser_tab_close   — Close current tab
      browser_tab_next    — Switch to next tab
      browser_tab_prev    — Switch to previous tab
      browser_tab_reopen  — Reopen last closed tab
      browser_tab_switch val — Switch to tab number (1-9)
      browser_bookmark    — Bookmark current page
      browser_bookmarks   — Open bookmarks manager
      browser_history     — Open browser history
      browser_downloads   — Open downloads page
      browser_find        — Find in page
      browser_refresh     — Refresh page
      browser_back        — Navigate back
      browser_forward     — Navigate forward
      browser_open_url name — Open URL (name=URL)
      browser_search name — Search in new tab (name=query)
      browser_fullscreen  — Toggle fullscreen
      browser_zoom_in     — Zoom in
      browser_zoom_out    — Zoom out
      browser_zoom_reset  — Reset zoom to 100%
      browser_incognito   — Open incognito window
      browser_devtools    — Open developer tools
      
      # WiFi & Bluetooth
      wifi_scan           — Scan nearby networks
      wifi_connect ssid [password] — Connect to WiFi
      wifi_disconnect     — Disconnect WiFi
      wifi_status         — Current WiFi status
      wifi_toggle state   — Enable/disable WiFi (on/off)
      bt_status           — Bluetooth status
      bt_toggle state     — Enable/disable Bluetooth (on/off)
      bt_list             — List paired BT devices
      bt_remove name      — Remove/unpair BT device by name
    """
    if action.startswith("wifi_"):
        act = action.replace("wifi_", "")
        result = handle_wifi(act, ssid or name, password, state)
    elif action.startswith("bt_"):
        act = action.replace("bt_", "")
        result = handle_bt(act, name, state)
    elif action.startswith("browser_"):
        # Browser automation via keyboard shortcuts
        from ..handlers.browser_ops import handle_browser
        act = action.replace("browser_", "")
        result = handle_browser(act, val, name, state)
    else:
        result = handle_pc(action, val, name, state, cmd)
    
    # Enforce language consistency on pc operation results
    try:
        current_style = get_latest_conversation_style()
        if isinstance(result, str) and current_style != "english":
            result = enforce_style(result, current_style)
    except Exception:
        pass  # Language enforcement is best-effort
        
    return result
