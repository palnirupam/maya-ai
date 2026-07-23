import subprocess, os, re, tempfile
from xml.sax.saxutils import escape as _xml_escape


def _run(cmd, timeout=10):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _sanitize_ssid(ssid: str) -> str:
    """SSIDs are max 32 chars; strip control chars and quotes so the value is
    safe both inside the WLAN profile XML and as a netsh argument."""
    return re.sub(r"[\x00-\x1f\"]", "", ssid or "").strip()[:32]


def wifi_scan() -> str:
    """Scan nearby Wi-Fi networks. Returns list with SSID, signal, security."""
    try:
        r = _run(["netsh", "wlan", "show", "networks", "mode=Bssid"], 15)
        if r.returncode != 0:
            return f"ERR: WiFi scan failed ({r.stderr.strip()})"
        out = r.stdout
        if "There are no networks" in out:
            return "No networks found. WiFi adapter may be off."
        results = []
        for line in out.splitlines():
            if line.startswith("SSID") and ":" in line:
                ssid = line.split(":", 1)[-1].strip()
                if ssid:
                    results.append(f"  {ssid}")
        return "Available WiFi networks:\n" + "\n".join(results) if results else "No networks found."
    except subprocess.TimeoutExpired:
        return "ERR: WiFi scan timed out"
    except Exception as e:
        return f"ERR: {e}"


def _build_wlan_xml(ssid: str, password: str = "") -> str:
    # XML-escape both values: an SSID/password containing <, &, or quotes must
    # not be able to alter the profile structure (XML injection).
    ssid = _xml_escape(ssid)
    password = _xml_escape(password or "")
    pw = f"""<MSM><security>
<authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption></authEncryption>
<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>{password}</keyMaterial></sharedKey>
</security></MSM>""" if password else "<MSM><security><authEncryption><authentication>open</authentication><encryption>none</encryption></authEncryption></security></MSM>"
    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
<name>{ssid}</name>
<SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
<connectionType>ESS</connectionType>
{pw}
</WLANProfile>"""


def wifi_connect(ssid: str, password: str = "") -> str:
    """Connect to a Wi-Fi network. Password required for secured networks."""
    try:
        ssid = _sanitize_ssid(ssid)
        if not ssid:
            return "ERR: Invalid or empty SSID."
        xml = _build_wlan_xml(ssid, password)
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False)
        tf.write(xml)
        tf.close()
        try:
            _run(["netsh", "wlan", "add", "profile", f"filename={tf.name}"], 5)
            r = _run(["netsh", "wlan", "connect", f"name={ssid}"], 15)
            return f"OK: Connecting to {ssid}..." if r.returncode == 0 else f"ERR: {r.stderr.strip() or r.stdout.strip()}"
        finally:
            os.unlink(tf.name)
    except subprocess.TimeoutExpired:
        return "ERR: WiFi connect timed out"
    except Exception as e:
        return f"ERR: {e}"


def wifi_disconnect() -> str:
    """Disconnect from current Wi-Fi network."""
    try:
        r = _run(["netsh", "wlan", "disconnect"])
        return "OK: Disconnected from WiFi." if r.returncode == 0 else f"ERR: {r.stderr.strip()}"
    except Exception as e:
        return f"ERR: {e}"


def wifi_status() -> str:
    """Show current WiFi connection status: SSID, signal."""
    try:
        r = _run(["netsh", "wlan", "show", "interfaces"])
        if r.returncode != 0:
            return "ERR: No WiFi adapter found."
        out = r.stdout
        if "There is no wireless interface" in out:
            return "No WiFi adapter detected."
        ssid = signal = ""
        for line in out.splitlines():
            if "SSID" in line and "BSSID" not in line:
                ssid = line.split(":", 1)[-1].strip()
            if "Signal" in line:
                signal = line.split(":", 1)[-1].strip()
        return f"WiFi: Connected\nSSID: {ssid}\nSignal: {signal}" if ssid else "WiFi: Disconnected"
    except Exception as e:
        return f"ERR: {e}"


def _wifi_interface_name() -> str:
    """The real wireless interface name ('Wi-Fi', 'WLAN', ...) — hardcoding
    'Wi-Fi' silently breaks toggling on systems that name it differently."""
    try:
        r = _run(["netsh", "wlan", "show", "interfaces"])
        for line in r.stdout.splitlines():
            s = line.strip()
            if s.lower().startswith("name") and ":" in s:
                name = s.split(":", 1)[-1].strip()
                if name:
                    return name
    except Exception:
        pass
    return "Wi-Fi"


def wifi_toggle(state: str = "on") -> str:
    """Enable or disable the WiFi adapter. state: 'on' or 'off'."""
    try:
        # Empty/None state means "on" (parity with bluetooth_toggle).
        want_on = (state or "on").strip().lower() in ("on", "enable", "1", "true", "")
        action = "enable" if want_on else "disable"
        iface = _wifi_interface_name()
        r = _run(["netsh", "interface", "set", "interface", f"name={iface}", f"admin={action}"])
        if r.returncode == 0:
            return f"OK: WiFi turned {'on' if want_on else 'off'}."
        detail = (r.stderr.strip() or r.stdout.strip())
        return f"ERR: Could not toggle WiFi — Administrator rights may be required. {detail}"
    except Exception as e:
        return f"ERR: {e}"
