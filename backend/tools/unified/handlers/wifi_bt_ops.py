"""WiFi + Bluetooth implementations."""


def handle_wifi(action, ssid="", password="", state=""):
    # Single hardened implementation lives in wifi_tools (input sanitization,
    # XML escaping, dynamic interface name). Delegate to it — same pattern as
    # handle_bt below.
    from ...desktop.advanced.wifi_tools import (
        wifi_scan, wifi_connect, wifi_disconnect, wifi_status, wifi_toggle,
    )

    if action == "scan":
        return wifi_scan()

    if action == "connect":
        return wifi_connect(ssid, password)

    if action == "disconnect":
        return wifi_disconnect()

    if action == "status":
        return wifi_status()

    if action in ("toggle", "on", "off"):
        st = state or ("off" if action == "off" else "on")
        return wifi_toggle(st)

    return f"ERR: unknown wifi action '{action}'"


def handle_bt(action, name="", state=""):
    # Single robust implementation lives in bluetooth_tools (WinRT Radio API,
    # works without Admin and verifies the real state). Delegate to it.
    from ...desktop.advanced.bluetooth_tools import (
        bluetooth_status, bluetooth_toggle, bluetooth_list_devices, bluetooth_remove_device,
    )

    if action == "status":
        return bluetooth_status()

    if action in ("toggle", "on", "off"):
        st = state or ("off" if action == "off" else "on")
        return bluetooth_toggle(st)

    if action == "list":
        return bluetooth_list_devices()

    if action == "remove":
        return bluetooth_remove_device(name)

    return f"ERR: unknown bt action '{action}'"
