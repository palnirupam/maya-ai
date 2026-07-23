"""LLM-facing pc (system control) router — single tool covers 20+ actions."""
from ..handlers.system_ops import handle_pc
from ..handlers.wifi_bt_ops import handle_wifi, handle_bt


def pc(action: str = "", val: int = 0, name: str = "", state: str = "", cmd: str = "", ssid: str = "", password: str = "") -> str:
    """
    Universal system control router.

    Actions (action parameter):
      volume val          — Set volume 0-100
      brightness val      — Set brightness 0-100
      lock                — Lock PC (Win+L)
      mute                — Toggle mute
      screenshot          — Capture screenshot (returns base64)
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
        return handle_wifi(act, ssid or name, password, state)
    if action.startswith("bt_"):
        act = action.replace("bt_", "")
        return handle_bt(act, name, state)
    return handle_pc(action, val, name, state, cmd)
