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

    return f"ERR: unknown pc action '{action}'"
