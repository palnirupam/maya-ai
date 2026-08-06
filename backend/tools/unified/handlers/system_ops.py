"""System control implementations — volume, brightness, lock, shutdown, process, battery, network."""
import subprocess, psutil
import pyautogui, pyperclip

from ..core.policy import is_safe_path


def _ps(cmd, timeout=10):
    try:
        r = subprocess.run(["powershell", "-NoProfile", cmd], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"ERR: {e}"


def _run_power_command(args, success_message):
    """Run a Windows power command and only report success on exit code zero."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except Exception as exc:
        return f"ERR: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
        return f"ERR: {detail}"
    return success_message


def _process_kill_is_protected(proc) -> bool:
    """Keep the generic process tool from bypassing app-control safeguards."""
    from ...desktop.apps import _is_protected_runtime_process, _is_system_process

    return _is_system_process(proc) or _is_protected_runtime_process(proc)


def _process_label(proc) -> str:
    info = getattr(proc, "info", None)
    if isinstance(info, dict) and info.get("name"):
        return str(info["name"])
    try:
        return str(proc.name())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return f"PID {getattr(proc, 'pid', '?')}"


def _kill_and_verify_process(proc) -> tuple[str, str]:
    """Refuse protected targets and wait until a requested process has exited."""
    label = _process_label(proc)
    try:
        if _process_kill_is_protected(proc):
            return "protected", label
        proc.kill()
        proc.wait(timeout=3)
        return "killed", label
    except psutil.NoSuchProcess:
        # The requested end state has already been reached.
        return "killed", label
    except psutil.TimeoutExpired:
        return "failed", f"{label}: still running after kill request"
    except psutil.AccessDenied:
        return "failed", f"{label}: access denied"
    except Exception as exc:
        return "failed", f"{label}: {exc}"


def handle_pc(action, val=0, name="", state="", cmd=""):
    if action == "volume":
        if not (0 <= val <= 100):
            return "ERR: volume 0-100"
        # Delegate to the CoreAudio COM API implementation in system_tools.py.
        # The previous inline PowerShell snippet used `[Audio]::Volume` — a type
        # accelerator that does NOT exist in PowerShell, causing a runtime crash.
        from ...desktop.advanced.system_tools import change_volume
        return change_volume(val)

    if action == "brightness":
        if not (0 <= val <= 100):
            return "ERR: brightness 0-100"
        # WmiSetBrightness returns 0 on success. `_ps` swallows its own errors and
        # returns stdout only, so the OLD code's try/except never fired and it
        # claimed "OK" even on machines without WmiMonitorBrightnessMethods
        # (desktops / many external monitors). Check the real ReturnValue instead.
        out = _ps(
            "$ErrorActionPreference='Stop'; "
            f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{val}).ReturnValue"
        )
        if out.strip() == "0":
            return f"OK: brightness {val}%"
        try:
            pyautogui.press("brightness" + ("up" if val > 50 else "down"))
            return "OK: brightness adjusted (approx — WMI not available)"
        except Exception as e:
            return f"ERR: brightness not supported on this display ({e})"

    if action == "lock":
        try:
            pyautogui.hotkey("win", "l")
            return "OK: locked"
        except Exception as e:
            return f"ERR: {e}"

    if action == "mute":
        try:
            pyautogui.press("volumemute")
            return "OK: toggled mute"
        except Exception as e:
            return f"ERR: {e}"

    if action == "screenshot":
        try:
            # Keep the unified router behind the same sensitive-app detection
            # and visible privacy notification as the dedicated vision tool.
            from ...desktop.advanced.vision_tools import take_verified_screenshot
            return take_verified_screenshot()
        except Exception as e:
            return f"ERR: {e}"

    if action == "camera_photo":
        from ...system.camera import take_camera_photo

        return take_camera_photo()

    if action == "sleep":
        return _run_power_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Add-Type '[DllImport(\"powrprof.dll\",SetLastError=true)]"
                "public static extern bool SetSuspendState(bool,bool,bool);' "
                "-Name a -Pas)[a]::SetSuspendState($true,$false,$false)",
            ],
            "OK: sleep",
        )

    if action == "shutdown":
        return _run_power_command(
            ["shutdown", "/s", "/t", "5"],
            "OK: shutting down in 5s",
        )

    if action == "restart":
        return _run_power_command(
            ["shutdown", "/r", "/t", "5"],
            "OK: restarting in 5s",
        )

    if action == "hibernate":
        return _run_power_command(["shutdown", "/h"], "OK: hibernating")

    if action == "clipboard_read":
        try:
            return pyperclip.paste()
        except Exception as e:
            return f"ERR: {e}"

    if action == "clipboard_write":
        try:
            pyperclip.copy(name or state)
            return "OK: clipboard set"
        except Exception as e:
            return f"ERR: {e}"

    if action == "process_list":
        try:
            sort_key = {"cpu": "cpu_percent", "mem": "memory_percent"}.get(cmd or "cpu", "cpu_percent")
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    procs.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            procs.sort(key=lambda x: x.get(sort_key, 0) or 0, reverse=True)
            lines = [f"{'PID':>6} {'CPU%':>5} {'MEM%':>5}  Name"]
            for p in procs[:30]:
                lines.append(f"{p['pid']:>6} {p['cpu_percent'] or 0:>5.1f} {p['memory_percent'] or 0:>5.1f}  {p['name']}")
            return "\n".join(lines)
        except Exception as e:
            return f"ERR: {e}"

    if action == "process_kill":
        try:
            targets = []
            if val:
                try:
                    pid = int(val)
                except (TypeError, ValueError):
                    return "ERR: process id must be a positive integer"
                if pid <= 0:
                    return "ERR: process id must be a positive integer"
                targets = [psutil.Process(pid)]
            else:
                query = str(name or "").strip().casefold()
                if not query:
                    return "ERR: process id or name is required"
                for proc in psutil.process_iter(["pid", "name"]):
                    proc_name = (proc.info.get("name") or "").casefold()
                    if query in proc_name:
                        targets.append(proc)

            if not targets:
                return "No matching process"

            killed, protected, failures = [], [], []
            for proc in targets:
                outcome, label = _kill_and_verify_process(proc)
                if outcome == "killed":
                    killed.append(label)
                elif outcome == "protected":
                    protected.append(label)
                else:
                    failures.append(label)

            if killed and (protected or failures):
                details = []
                if protected:
                    details.append("protected system/Maya runtime process kept running")
                if failures:
                    details.append(f"{len(failures)} target(s) could not be verified stopped")
                return f"PARTIAL: killed {', '.join(killed[:8])}; {'; '.join(details)}."
            if killed:
                return f"OK: killed {', '.join(killed[:8])}"
            if protected:
                return "ERR: Refused to kill a protected system or Maya/runtime process."
            return f"ERR: Could not verify process termination: {'; '.join(failures[:3])}"
        except Exception as exc:
            return f"ERR: {exc}"

    if action == "battery":
        try:
            batt = psutil.sensors_battery()
            if not batt:
                return "No battery detected"
            plug = "Charging" if batt.power_plugged else "On battery"
            secs = batt.secsleft
            time_s = ""
            if secs not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
                h, m = divmod(secs // 60, 60)
                time_s = f" ({h}h{m}m)" if not batt.power_plugged else f" ({h}h{m}m to full)"
            try:
                plan = _ps("(Get-CimInstance -Namespace root\\cimv2\\power -ClassName Win32_PowerPlan -Filter 'IsActive=True').ElementName")
                if not plan or plan.startswith("ERR:"):
                    plan = "n/a"
            except Exception:
                plan = "n/a"
            return f"Battery: {batt.percent:.0f}% {plug}{time_s}\nPlan: {plan}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "network":
        try:
            import socket
            hostname = socket.gethostname()
            local_ip = "n/a"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("1.1.1.1", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                pass
            lines = [f"Host: {hostname}", f"IP: {local_ip}"]
            for name_i, addrs in psutil.net_if_addrs().items():
                if name_i.startswith("Loopback"):
                    continue
                stats = psutil.net_if_stats().get(name_i)
                up = "Up" if stats and stats.isup else "Down"
                ips = [a.address for a in addrs if a.family.name == "AF_INET"]
                if ips:
                    lines.append(f"  {name_i}: {up} — {', '.join(ips)}")
            return "\n".join(lines)
        except Exception as e:
            return f"ERR: {e}"

    if action == "stats":
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return f"CPU: {cpu}%\nRAM: {mem.percent}% ({mem.used>>30}GB/{mem.total>>30}GB)\nDisk: {disk.percent}%"
        except Exception as e:
            return f"ERR: {e}"

    if action == "active_windows":
        try:
            r = subprocess.run('powershell "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object Name,MainWindowTitle"',
                               capture_output=True, text=True, shell=True, timeout=10)
            return f"Windows:\n{r.stdout}"
        except Exception as e:
            return f"ERR: {e}"

    # ── Multiple Monitor Configuration ──
    if action == "display_list":
        try:
            cmd = """
            Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBasicDisplayParams | 
            Select-Object InstanceName, 
            @{Name='Width';Expression={$_.MaxHorizontalImageSize}},
            @{Name='Height';Expression={$_.MaxVerticalImageSize}}
            """
            result = _ps(cmd)
            return f"Displays:\n{result}" if result and not result.startswith("ERR:") else "ERR: Could not list displays"
        except Exception as e:
            return f"ERR: {e}"

    if action == "display_settings":
        # Open Windows Display Settings
        try:
            subprocess.Popen(["start", "ms-settings:display"], shell=True)
            return "OK: Opened Display Settings"
        except Exception as e:
            return f"ERR: {e}"

    if action == "display_orientation":
        # Rotate display: val = 0 (landscape), 1 (portrait), 2 (landscape flipped), 3 (portrait flipped)
        try:
            if val not in [0, 1, 2, 3]:
                return "ERR: orientation must be 0-3 (0=landscape, 1=portrait, 2=landscape flipped, 3=portrait flipped)"
            cmd = f"""
            $ErrorActionPreference='Stop';
            Add-Type -AssemblyName System.Windows.Forms;
            $screen = [System.Windows.Forms.Screen]::PrimaryScreen;
            $device = New-Object DEVMODE;
            $device.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($device);
            [DisplayConfig]::EnumDisplaySettings($screen.DeviceName, -1, [ref]$device);
            $device.dmDisplayOrientation = {val};
            [DisplayConfig]::ChangeDisplaySettingsEx($screen.DeviceName, [ref]$device, 0, 0, 0);
            """
            result = _ps(cmd)
            return f"OK: Display orientation changed to {['landscape', 'portrait', 'landscape flipped', 'portrait flipped'][val]}"
        except Exception as e:
            return f"ERR: Display orientation change not supported ({e})"

    if action == "display_extend":
        # Extend/duplicate displays using Win+P shortcut
        try:
            pyautogui.hotkey("win", "p")
            import time; time.sleep(0.5)
            # Press arrow key based on mode: name = "pc_only" | "duplicate" | "extend" | "second_only"
            arrow_map = {"pc_only": "up", "duplicate": "down", "extend": "down", "second_only": "down"}
            presses = {"pc_only": 0, "duplicate": 1, "extend": 2, "second_only": 3}
            mode = name.lower() if name else "extend"
            if mode not in presses:
                return "ERR: display mode must be 'pc_only', 'duplicate', 'extend', or 'second_only'"
            for _ in range(presses[mode]):
                pyautogui.press("down")
                time.sleep(0.1)
            pyautogui.press("enter")
            return f"OK: Display mode set to '{mode}'"
        except Exception as e:
            return f"ERR: {e}"

    # ── Keyboard Shortcut Customization ──
    if action == "hotkey_remap":
        # Create AutoHotkey script to remap keys
        # Requires: name = "source_key", state = "target_key"
        try:
            if not name or not state:
                return "ERR: hotkey_remap requires 'name' (source key) and 'state' (target key)"
            
            import os
            ahk_script_path = os.path.expanduser("~/maya_hotkey_remap.ahk")
            
            # Read existing script if it exists
            existing_mappings = []
            if os.path.exists(ahk_script_path):
                with open(ahk_script_path, "r", encoding="utf-8") as f:
                    existing_mappings = f.readlines()
            
            # Add new mapping
            new_mapping = f"{name}::{state}\n"
            if new_mapping not in existing_mappings:
                existing_mappings.append(new_mapping)
            
            # Write updated script
            with open(ahk_script_path, "w", encoding="utf-8") as f:
                f.writelines(existing_mappings)
            
            # Check if AutoHotkey is installed
            ahk_paths = [
                r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
                r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe",
            ]
            ahk_exe = None
            for path in ahk_paths:
                if os.path.exists(path):
                    ahk_exe = path
                    break
            
            if ahk_exe:
                # Kill existing AutoHotkey process and restart
                subprocess.run(["taskkill", "/F", "/IM", "AutoHotkey.exe"], 
                             capture_output=True, timeout=5)
                subprocess.Popen([ahk_exe, ahk_script_path])
                return f"OK: Remapped '{name}' → '{state}' (AutoHotkey script: {ahk_script_path})"
            else:
                return f"OK: Remap script created at {ahk_script_path}, but AutoHotkey is not installed. Install from autohotkey.com"
        except Exception as e:
            return f"ERR: {e}"

    if action == "hotkey_list":
        # List current remapped hotkeys
        try:
            import os
            ahk_script_path = os.path.expanduser("~/maya_hotkey_remap.ahk")
            if not os.path.exists(ahk_script_path):
                return "No custom hotkey remappings found"
            with open(ahk_script_path, "r", encoding="utf-8") as f:
                mappings = f.read()
            return f"Custom Hotkey Mappings:\n{mappings}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "hotkey_reset":
        # Remove all hotkey remappings
        try:
            import os
            ahk_script_path = os.path.expanduser("~/maya_hotkey_remap.ahk")
            if os.path.exists(ahk_script_path):
                os.remove(ahk_script_path)
            subprocess.run(["taskkill", "/F", "/IM", "AutoHotkey.exe"], 
                         capture_output=True, timeout=5)
            return "OK: All hotkey remappings cleared"
        except Exception as e:
            return f"ERR: {e}"

    # ── System Theme/Appearance ──
    if action == "theme_dark":
        try:
            val_mode = 0 if val == 1 else 1  # val=1 means dark mode ON
            cmd = f'Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name AppsUseLightTheme -Value {val_mode}'
            _ps(cmd)
            cmd2 = f'Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name SystemUsesLightTheme -Value {val_mode}'
            _ps(cmd2)
            return f"OK: {'Dark' if val == 1 else 'Light'} mode enabled"
        except Exception as e:
            return f"ERR: {e}"

    if action == "theme_accent":
        # Change Windows accent color (val = color hex without #, e.g., "FF0000" for red)
        try:
            if not name:
                return "ERR: accent color hex required in 'name' parameter (e.g., 'FF0000')"
            
            # Convert hex to BGR integer (Windows uses BGR, not RGB)
            color_hex = name.strip().replace("#", "")
            if len(color_hex) != 6:
                return "ERR: color must be 6-digit hex (e.g., 'FF0000')"
            
            r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
            bgr_int = (b << 16) | (g << 8) | r
            
            cmd = f"""
            Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\DWM -Name AccentColor -Value {bgr_int};
            Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\DWM -Name ColorizationColor -Value {bgr_int};
            Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name ColorPrevalence -Value 1;
            """
            _ps(cmd)
            return f"OK: Accent color set to #{color_hex.upper()} (restart Explorer to apply)"
        except Exception as e:
            return f"ERR: {e}"

    if action == "theme_wallpaper":
        # Change desktop wallpaper (name = image path)
        try:
            if not name:
                return "ERR: wallpaper image path required in 'name' parameter"
            
            import os
            if not os.path.exists(name):
                return f"ERR: wallpaper file not found: {name}"
            
            import ctypes
            SPI_SETDESKWALLPAPER = 20
            ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, name, 3)
            
            # Track in wallpaper history
            try:
                from .wallpaper_manager import wallpaper_manager
                theme = state or "custom"  # Use state param for theme name
                wallpaper_manager.add_to_history(name, theme)
            except Exception:
                pass  # Don't fail if history tracking fails
            
            return f"OK: Wallpaper set to {name}"
        except Exception as e:
            return f"ERR: {e}"

    if action == "theme_transparency":
        # Enable/disable transparency effects (val = 1 for ON, 0 for OFF)
        try:
            cmd = f'Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name EnableTransparency -Value {val}'
            _ps(cmd)
            return f"OK: Transparency {'enabled' if val == 1 else 'disabled'}"
        except Exception as e:
            return f"ERR: {e}"

    # ── Notification Center Interaction ──
    if action == "notification_open":
        try:
            pyautogui.hotkey("win", "n")
            return "OK: Opened Notification Center"
        except Exception as e:
            return f"ERR: {e}"

    if action == "notification_clear":
        # Clear all notifications
        try:
            pyautogui.hotkey("win", "n")
            import time; time.sleep(0.5)
            # Click "Clear all" button (approximate position, may need adjustment)
            pyautogui.hotkey("tab")
            time.sleep(0.2)
            pyautogui.press("enter")
            return "OK: Cleared all notifications"
        except Exception as e:
            return f"ERR: {e}"

    if action == "notification_list":
        # List recent notifications (reads from Windows notification database)
        try:
            cmd = """
            $notifications = Get-WinEvent -LogName 'Microsoft-Windows-PushNotifications-Platform/Operational' -MaxEvents 10 -ErrorAction SilentlyContinue |
            Select-Object TimeCreated, Message | Format-Table -AutoSize
            $notifications
            """
            result = _ps(cmd)
            return f"Recent Notifications:\n{result}" if result and not result.startswith("ERR:") else "No recent notifications"
        except Exception as e:
            return f"ERR: {e}"

    if action == "notification_focus":
        # Toggle Focus Assist mode (Do Not Disturb)
        try:
            # Open Focus Assist settings
            subprocess.Popen(["start", "ms-settings:quiethours"], shell=True)
            return "OK: Opened Focus Assist settings"
        except Exception as e:
            return f"ERR: {e}"

    # ── Wallpaper Feedback & Management ──
    if action == "wallpaper_dislike":
        # User doesn't like current wallpaper - try alternative
        try:
            from .wallpaper_manager import handle_wallpaper_feedback
            theme = name or "abstract"  # Use name param for theme
            result = handle_wallpaper_feedback("dislike", theme)
            return result
        except Exception as e:
            return f"ERR: {e}"
    
    if action == "wallpaper_restore":
        # Restore previous wallpaper
        try:
            from .wallpaper_manager import handle_wallpaper_feedback
            result = handle_wallpaper_feedback("restore")
            return result
        except Exception as e:
            return f"ERR: {e}"
    
    if action == "wallpaper_suggest":
        # Suggest alternative themes
        try:
            from .wallpaper_manager import handle_wallpaper_feedback
            theme = name or None
            result = handle_wallpaper_feedback("suggest", theme)
            return result
        except Exception as e:
            return f"ERR: {e}"
    
    if action == "wallpaper_like":
        # User likes current wallpaper
        try:
            from .wallpaper_manager import handle_wallpaper_feedback
            result = handle_wallpaper_feedback("like")
            return result
        except Exception as e:
            return f"ERR: {e}"

    return f"ERR: unknown pc action '{action}'"
