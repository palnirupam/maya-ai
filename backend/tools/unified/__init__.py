"""Unified Maya tool API — token-efficient router-based interface.

Usage (LLM-facing, 4 tools total):
  file(action, src, dst, name, n, path)  — All file operations
  pc(action, val, name, state, cmd)      — All system + wifi + bt control
  channel(action, target, msg, file)      — Messaging (Telegram/WhatsApp)
  browser(action, url, query, ...)        — Web/browser actions
"""
from .dispatchers.file_router import file
from .dispatchers.pc_router import pc

# Legacy backward-compatible aliases (will be removed in future)
from ..desktop.advanced.file_system_tools import (
    create_file, read_file, list_directory, delete_file, search_local_files,
    organize_folder, move_file, move_items, copy_file, create_folder,
    delete_folder, rename_file, delete_by_name,
)
from ..desktop.advanced.system_tools import (
    get_active_windows, change_volume, read_clipboard, write_clipboard,
    get_system_stats, manage_processes, read_on_screen_text,
    list_processes, get_battery_info, get_network_info,
)
from ..desktop.advanced.wifi_tools import (
    wifi_scan, wifi_connect, wifi_disconnect, wifi_status, wifi_toggle,
)
from ..desktop.advanced.bluetooth_tools import (
    bluetooth_status, bluetooth_toggle, bluetooth_list_devices, bluetooth_remove_device,
)

__all__ = [
    "file", "pc",
    "create_file", "read_file", "list_directory", "delete_file", "search_local_files",
    "organize_folder", "move_file", "move_items", "copy_file", "create_folder",
    "delete_folder", "rename_file", "delete_by_name",
    "get_active_windows", "change_volume", "read_clipboard", "write_clipboard",
    "get_system_stats", "manage_processes", "read_on_screen_text",
    "list_processes", "get_battery_info", "get_network_info",
    "wifi_scan", "wifi_connect", "wifi_disconnect", "wifi_status", "wifi_toggle",
    "bluetooth_status", "bluetooth_toggle", "bluetooth_list_devices", "bluetooth_remove_device",
]
