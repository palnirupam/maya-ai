import subprocess, re


def _ps(cmd: str, timeout=10) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", cmd], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"ERR: {e}"


# WinRT Radio prelude — toggles the Bluetooth radio exactly like the Windows
# Action Center switch. Unlike Enable/Disable-PnpDevice it does NOT require
# Administrator rights and reports the *real* resulting state, so we can verify
# the change instead of blindly claiming success.
_RADIO_PRELUDE = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($t, $type) {
    $m = $asTaskGeneric.MakeGenericMethod($type)
    $nt = $m.Invoke($null, @($t))
    $nt.Wait(-1) | Out-Null
    $nt.Result
}
[Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus, Windows.System.Devices, ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioState, Windows.System.Devices, ContentType=WindowsRuntime] | Out-Null
function Get-BtRadio {
    $access = Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus])
    if ("$access" -ne 'Allowed') { return $null }
    $radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
    return ($radios | Where-Object { "$($_.Kind)" -eq 'Bluetooth' } | Select-Object -First 1)
}
"""


def _paired_count() -> str:
    paired = _ps('(Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -notmatch "radio|adapter|enumerator" }).Count')
    return paired if paired and not paired.startswith("ERR") else "?"


def bluetooth_status() -> str:
    """Check if Bluetooth is enabled and show paired devices count."""
    try:
        out = _ps(_RADIO_PRELUDE + """
$bt = Get-BtRadio
if ($bt) { "STATE:$($bt.State)" } else { 'NO_RADIO_API' }
""", 25)
        m = re.search(r"STATE:(\w+)", out or "")
        if m:
            return f"Bluetooth: {m.group(1).lower()}\nPaired devices: {_paired_count()}"
        # Fallback: read the PnP device status (read-only, no admin needed).
        status = _ps("""
$a = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match 'bluetooth|radio|adapter' -and $_.FriendlyName -notmatch 'enumerator' } | Select-Object -First 1
if ($a) { if ($a.Status -eq 'OK') { 'on' } else { 'off' } } else { 'no adapter' }
""")
        return f"Bluetooth: {status or 'unknown'}\nPaired devices: {_paired_count()}"
    except Exception as e:
        return f"ERR: {e}"


def _bluetooth_toggle_pnp(want_on: bool) -> str:
    """Fallback toggle via Enable/Disable-PnpDevice. Requires Administrator;
    reports success ONLY when the operation truly succeeds (no silent OK)."""
    action = "Enable" if want_on else "Disable"
    r = _ps(f"""
$a = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object {{ $_.FriendlyName -match 'bluetooth|radio|adapter' -and $_.FriendlyName -notmatch 'enumerator' }} | Select-Object -First 1
if (-not $a) {{ 'no adapter' }}
else {{
    try {{ $a | {action}-PnpDevice -Confirm:$false -ErrorAction Stop | Out-Null; "OK:$($a.FriendlyName)" }}
    catch {{ "FAIL:$($_.Exception.Message)" }}
}}
""", 20)
    if r.startswith("OK:"):
        return f"OK: Bluetooth turned {'on' if want_on else 'off'}."
    if "no adapter" in r:
        return "ERR: No Bluetooth adapter found."
    return f"ERR: Could not toggle Bluetooth — Administrator rights required. Details: {r}"


def bluetooth_toggle(state: str = "on") -> str:
    """Enable or disable Bluetooth. state: 'on' or 'off'."""
    try:
        want_on = state.strip().lower() in ("on", "enable", "1", "true", "")
        target = "On" if want_on else "Off"
        out = _ps(_RADIO_PRELUDE + f"""
$bt = Get-BtRadio
if (-not $bt) {{ 'NO_RADIO_API' }}
else {{
    Await ($bt.SetStateAsync([Windows.Devices.Radios.RadioState]::{target})) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
    $bt2 = Get-BtRadio
    if ($bt2) {{ "STATE:$($bt2.State)" }} else {{ 'UNKNOWN' }}
}}
""", 25)
        m = re.search(r"STATE:(\w+)", out or "")
        if m:
            # Only report success when the radio actually reached the target state.
            if m.group(1).lower() == target.lower():
                return f"OK: Bluetooth turned {target.lower()}."
            return f"ERR: Bluetooth is still {m.group(1).lower()} — toggle did not take effect."
        # Radio API unavailable (older Windows) → fall back to PnP enable/disable.
        if not out or "NO_RADIO_API" in out or out.startswith("ERR"):
            return _bluetooth_toggle_pnp(want_on)
        return f"ERR: Bluetooth toggle failed. {out}"
    except Exception as e:
        return f"ERR: {e}"


def bluetooth_list_devices() -> str:
    """List paired Bluetooth devices with name and type."""
    try:
        r = _ps("""
Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue |
    Where-Object { $_.FriendlyName -notmatch 'radio|adapter' } |
    Select-Object FriendlyName, Status, Class |
    ConvertTo-Json
""", 10)
        if not r or r == "ERR:":
            return "No paired devices found."
        import json
        data = json.loads(r)
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No paired devices found."
        lines = [f"Paired devices ({len(items)}):"]
        for d in items:
            name = d.get("FriendlyName", "?")
            status = "✅ Connected" if d.get("Status") == "OK" else "❌ Disconnected"
            lines.append(f"  {name} — {status}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERR: {e}"


def bluetooth_remove_device(name: str) -> str:
    """Remove/unpair a Bluetooth device by name."""
    # Allow-list the name before interpolating into PowerShell: blocks command
    # injection (quotes, $(), ;) and regex metacharacters inside -match.
    safe = re.sub(r"[^\w \-]", "", name or "").strip()[:64]
    if not safe:
        return "ERR: Invalid device name."
    try:
        r = _ps(f"""
$dev = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue |
    Where-Object {{ $_.FriendlyName -match '{safe}' }} |
    Select-Object -First 1
if ($dev) {{
    try {{
        $dev | Disable-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
        $dev | Remove-PnpDevice -Confirm:$false -ErrorAction Stop | Out-Null
        'removed'
    }} catch {{ "FAIL:$($_.Exception.Message)" }}
}} else {{ 'not found' }}
""", 15)
        if "removed" in r:
            return f"OK: Removed Bluetooth device '{safe}'."
        if "FAIL:" in r:
            return f"ERR: Could not remove '{safe}' — Administrator rights may be required."
        return f"ERR: Device '{safe}' not found."
    except Exception as e:
        return f"ERR: {e}"
