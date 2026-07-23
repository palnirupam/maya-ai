"""
Maya AI — Smart App Launcher
Opens Windows applications intelligently using multiple strategies.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import time
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Shell surfaces and Maya itself are infrastructure, not user apps. Bulk-close
# commands must never dismiss them even when the user only names another app to
# preserve.
_BULK_CLOSE_PROTECTED_TITLES = {"program manager", "maya ai"}
_PROTECTED_APP_NAMES = {"maya", "maya ai", "maya-ai"}
_PROTECTED_RUNTIME_PROCESS_NAMES = {"python", "pythonw", "node", "maya", "maya-ai"}
_PROTECTED_HOST_PROCESS_NAMES = {
    "code",
    "codex",
    "devenv",
    "pycharm64",
    "wt",
}
_UNSAFE_APP_QUERY_RE = re.compile(r"[;&|`$%<>^\\/()]|\r|\n")

# Common spoken/typed variants that should resolve before fuzzy matching.
APP_NAME_ALIASES = {
    "wa": "whatsapp",
    "whatapp": "whatsapp",
    "whatsap": "whatsapp",
    "watsapp": "whatsapp",
    "whats app": "whatsapp",
    "yt": "youtube",
    "yt video": "youtube",
    "youtube video": "youtube",
    "yt song": "youtube",
    "youtube song": "youtube",
    "yt music": "youtube",
    "youtube music": "youtube",
    "cmd prompt": "cmd",
    "command prompt": "cmd",
    "files": "file explorer",
    "file manager": "file explorer",
}

APP_COMMAND_WORDS = {
    "a", "an", "any", "app", "application", "apps", "chalao", "chalu",
    "band", "bondho", "close", "do", "eta", "focus", "je", "jekono", "jokono", "khol", "khole", "kholje",
    "kholo", "khul", "khule", "khulo", "khulte", "kor", "kore", "koro",
    "korte", "launch", "maya", "open", "please", "pls", "start", "switch", "ta", "the",
}

# Comprehensive app registry: maps common names → launch strategies
APP_REGISTRY = {
    # Browsers
    "chrome": {"exe": "chrome.exe", "paths": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]},
    "firefox": {"exe": "firefox.exe", "paths": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ]},
    "edge": {"exe": "msedge.exe", "paths": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]},
    "browser": {"alias": "chrome"},
    "google chrome": {"alias": "chrome"},

    # Communication
    "whatsapp": {
        "protocol": "whatsapp://",
        "ms_store": "WhatsApp",
        "url_fallback": "https://web.whatsapp.com/",
    },
    "telegram": {"protocol": "tg://", "ms_store": "Telegram Desktop"},
    "discord": {"ms_store": "Discord", "exe": "Discord.exe", "paths": [
        os.path.expandvars(r"%LocalAppData%\Discord\Update.exe"),
    ]},
    "zoom": {"exe": "Zoom.exe", "paths": [
        os.path.expandvars(r"%AppData%\Zoom\bin\Zoom.exe"),
    ]},
    "teams": {"protocol": "msteams:", "ms_store": "Microsoft Teams"},
    "slack": {"ms_store": "Slack", "exe": "slack.exe"},
    "skype": {"protocol": "skype:", "ms_store": "Skype"},

    # Productivity
    "notepad": {"exe": "notepad.exe"},
    "word": {"exe": "winword.exe", "paths": [
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    ]},
    "excel": {"exe": "excel.exe", "paths": [
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
    ]},
    "powerpoint": {"exe": "powerpnt.exe", "paths": [
        r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    ]},
    "outlook": {"exe": "outlook.exe"},
    "onenote": {"protocol": "onenote:"},

    # Code / Dev
    "vscode": {"exe": "code", "shell": True},
    "vs code": {"alias": "vscode"},
    "visual studio code": {"alias": "vscode"},
    "visual studio": {"exe": "devenv.exe"},
    "pycharm": {"exe": "pycharm64.exe"},
    "android studio": {"exe": "studio64.exe"},
    "git bash": {"exe": "git-bash.exe", "paths": [
        r"C:\Program Files\Git\git-bash.exe",
    ]},
    "postman": {"ms_store": "Postman", "exe": "Postman.exe"},
    "terminal": {"exe": "wt.exe"},  # Windows Terminal
    "cmd": {"exe": "cmd.exe"},
    "powershell": {"exe": "powershell.exe"},

    # Media
    "spotify": {"protocol": "spotify:", "ms_store": "Spotify"},
    "vlc": {"exe": "vlc.exe", "paths": [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]},
    "windows media player": {"exe": "wmplayer.exe"},
    "groove": {"protocol": "mswindowsmusic:"},
    "photos": {"protocol": "ms-photos:"},
    "camera": {"protocol": "microsoft.windows.camera:"},

    # System
    "settings": {"protocol": "ms-settings:"},
    "calculator": {"exe": "calc.exe"},
    "calc": {"alias": "calculator"},
    "paint": {"exe": "mspaint.exe"},
    "snipping tool": {"exe": "SnippingTool.exe"},
    "task manager": {"exe": "taskmgr.exe"},
    "file explorer": {"exe": "explorer.exe"},
    "explorer": {"alias": "file explorer"},
    "control panel": {"exe": "control.exe"},
    "device manager": {"exe": "devmgmt.msc", "shell": True},
    "regedit": {"exe": "regedit.exe"},
    "wordpad": {"exe": "wordpad.exe"},

    # Web apps (open in browser)
    "youtube": {"url": "https://www.youtube.com"},
    "gmail": {"url": "https://mail.google.com"},
    "google": {"url": "https://www.google.com"},
    "facebook": {"url": "https://www.facebook.com"},
    "twitter": {"url": "https://www.twitter.com"},
    "instagram": {"url": "https://www.instagram.com"},
    "netflix": {"url": "https://www.netflix.com"},
    "github": {"url": "https://www.github.com"},
    "linkedin": {"url": "https://www.linkedin.com"},
    "maps": {"url": "https://maps.google.com"},
    "google maps": {"alias": "maps"},
    "amazon": {"url": "https://www.amazon.in"},
    "flipkart": {"url": "https://www.flipkart.com"},
    "chat gpt": {"url": "https://chat.openai.com"},
    "chatgpt": {"url": "https://chat.openai.com"},
    "bard": {"url": "https://bard.google.com"},
    "gemini": {"url": "https://gemini.google.com"},

    # Games
    "steam": {"exe": "steam.exe", "paths": [
        r"C:\Program Files (x86)\Steam\steam.exe",
    ]},
    "epic games": {"exe": "EpicGamesLauncher.exe"},
    "free fire": {"url": "https://www.google.com/search?q=Free+Fire+PC+launch"},
    "minecraft": {"exe": "Minecraft.exe"},
}


def _resolve_alias(name: str) -> dict:
    """Resolve alias chains."""
    info = APP_REGISTRY.get(name, {})
    seen = set()
    while "alias" in info and info["alias"] not in seen:
        seen.add(info["alias"])
        info = APP_REGISTRY.get(info["alias"], {})
    return info


def _subprocess_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _popen(args, **kwargs):
    merged = _subprocess_kwargs()
    merged.update(kwargs)
    return subprocess.Popen(args, **merged)


def _simple_name(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9+#.]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_safe_app_query(value: str) -> bool:
    """App controls accept names only, never shell syntax or filesystem paths."""
    return bool(value and value.strip()) and not _UNSAFE_APP_QUERY_RE.search(value)


def _is_protected_app_query(value: str) -> bool:
    raw = _simple_name(value)
    words = [
        word
        for word in raw.split()
        if word not in APP_COMMAND_WORDS or word == "maya"
    ]
    return " ".join(words) in {"maya", "maya ai"}


def _normalize_app_query(app_name: str) -> str:
    if not _is_safe_app_query(app_name):
        return ""
    if _is_protected_app_query(app_name):
        return "maya ai"
    raw = _simple_name(app_name)
    if raw in APP_NAME_ALIASES:
        return APP_NAME_ALIASES[raw]

    words = [w for w in raw.split() if w not in APP_COMMAND_WORDS]
    cleaned = " ".join(words).strip()
    return APP_NAME_ALIASES.get(cleaned, cleaned)


def _best_registry_match(name_clean: str) -> tuple[str, float] | None:
    if name_clean in APP_REGISTRY:
        return name_clean, 100.0

    registry_keys = list(APP_REGISTRY.keys())
    try:
        from rapidfuzz import process, fuzz

        match_res = process.extractOne(
            name_clean,
            registry_keys,
            scorer=fuzz.WRatio,
            score_cutoff=75.0,
        )
        if match_res:
            matched_key, score, _ = match_res
            return matched_key, float(score)
    except ImportError:
        matches = difflib.get_close_matches(name_clean, registry_keys, n=1, cutoff=0.72)
        if matches:
            ratio = difflib.SequenceMatcher(None, name_clean, matches[0]).ratio() * 100
            return matches[0], ratio

    return None


def _startfile(target: str) -> bool:
    if not hasattr(os, "startfile"):
        return False
    try:
        os.startfile(target)
        return True
    except Exception as e:
        logger.warning(f"ShellExecute launch failed for {target}: {e}")
        return False


def _launch_protocol(protocol: str) -> bool:
    if _startfile(protocol):
        return True
    if os.name == "nt":
        try:
            _popen(["explorer.exe", protocol])
            return True
        except Exception as e:
            logger.warning(f"Protocol explorer launch failed for {protocol}: {e}")
    return False


def _launch_existing_path(path: str) -> bool:
    expanded = os.path.expandvars(path)
    if not os.path.exists(expanded):
        return False

    if _startfile(expanded):
        return True

    try:
        _popen([expanded])
        return True
    except Exception as e:
        logger.warning(f"Path launch failed for {expanded}: {e}")
        return False


def _launch_exe(exe: str) -> bool:
    expanded = os.path.expandvars(exe)

    if os.path.isabs(expanded) or os.sep in expanded:
        return _launch_existing_path(expanded)

    if expanded.lower().endswith((".msc", ".cpl")):
        return _startfile(expanded)

    resolved = shutil.which(expanded)
    if not resolved:
        return False

    try:
        _popen([resolved])
        return True
    except Exception as e:
        logger.warning(f"EXE launch failed for {expanded}: {e}")
        return False


@lru_cache(maxsize=1)
def _get_start_apps() -> tuple[tuple[str, str], ...]:
    """Return (display name, AppUserModelID) pairs from the Windows Start menu."""
    if os.name != "nt":
        return ()

    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return ()

    command = "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=8,
            **_subprocess_kwargs(),
        )
    except Exception as e:
        logger.warning(f"Get-StartApps failed: {e}")
        return ()

    if result.returncode != 0 or not result.stdout.strip():
        logger.debug(f"Get-StartApps returned no data: {result.stderr.strip()}")
        return ()

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.warning(f"Could not parse Get-StartApps JSON: {e}")
        return ()

    if isinstance(parsed, dict):
        parsed = [parsed]

    apps = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        appid = str(item.get("AppID") or "").strip()
        if name and appid:
            apps.append((name, appid))
    return tuple(apps)


@lru_cache(maxsize=1)
def _get_start_menu_shortcuts() -> tuple[tuple[str, str], ...]:
    if os.name != "nt":
        return ()

    roots = [
        os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
    ]
    shortcuts = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        try:
            for child in root_path.rglob("*"):
                if child.suffix.lower() in {".lnk", ".url"}:
                    shortcuts.append((child.stem, str(child)))
        except OSError as e:
            logger.debug(f"Could not scan Start menu folder {root}: {e}")
    return tuple(shortcuts)


def _score_name(query: str, candidate: str) -> float:
    q = _simple_name(query)
    c = _simple_name(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 100.0
    if q in c or c in q:
        return 95.0
    try:
        from rapidfuzz import fuzz

        return float(fuzz.WRatio(q, c))
    except ImportError:
        return difflib.SequenceMatcher(None, q, c).ratio() * 100


def _best_named_match(query: str, candidates: tuple[tuple[str, str], ...]) -> tuple[str, str] | None:
    best = None
    best_score = 0.0
    for display_name, payload in candidates:
        score = _score_name(query, display_name)
        if score > best_score:
            best = (display_name, payload)
            best_score = score
    return best if best and best_score >= 72.0 else None


def _launch_start_app(query: str, display_hint: str = "") -> str | None:
    candidates = _get_start_apps()
    if not candidates:
        return None

    for lookup in [display_hint, query]:
        if not lookup:
            continue
        match = _best_named_match(lookup, candidates)
        if not match:
            continue
        display_name, appid = match
        try:
            _popen(["explorer.exe", f"shell:AppsFolder\\{appid}"])
            return f"SUCCESS: Launched {display_name} from Windows Start Apps."
        except Exception as e:
            logger.warning(f"Start Apps launch failed for {display_name}: {e}")
    return None


def _launch_start_menu_shortcut(query: str, display_hint: str = "") -> str | None:
    candidates = _get_start_menu_shortcuts()
    if not candidates:
        return None

    for lookup in [display_hint, query]:
        if not lookup:
            continue
        match = _best_named_match(lookup, candidates)
        if not match:
            continue
        display_name, shortcut_path = match
        if _startfile(shortcut_path):
            return f"SUCCESS: Launched {display_name} from Start menu shortcut."
    return None


def _launch_via_windows_search(actual_name: str) -> str:
    try:
        import pyautogui

        pyautogui.hotkey("win", "s")
        time.sleep(0.7)
        pyautogui.write(actual_name, interval=0.04)
        time.sleep(0.9)
        pyautogui.press("enter")
        return f"SUCCESS: Searched and opened {actual_name} via Windows Search."
    except Exception as e:
        return f"ERROR: Could not open {actual_name}. {e}"


def _app_name_candidates(app_name: str) -> list[str]:
    normalized = _normalize_app_query(app_name) or _simple_name(app_name)
    candidates = []

    for value in [app_name, normalized]:
        simple = _simple_name(value)
        if simple and simple not in candidates:
            candidates.append(simple)

    match_res = _best_registry_match(normalized)
    if match_res:
        matched_key, _ = match_res
        canonical_key = matched_key
        seen = set()
        while canonical_key not in seen:
            seen.add(canonical_key)
            alias = APP_REGISTRY.get(canonical_key, {}).get("alias")
            if not alias:
                break
            canonical_key = alias

        alias_family = [
            key
            for key in APP_REGISTRY
            if key == canonical_key
            or APP_REGISTRY.get(key, {}).get("alias") == canonical_key
        ]
        for value in [
            matched_key,
            *alias_family,
            _resolve_alias(matched_key).get("ms_store", ""),
        ]:
            simple = _simple_name(value)
            if simple and simple not in candidates:
                candidates.append(simple)

    return candidates


def _text_matches_any(text: str, candidates: list[str]) -> bool:
    simple_text = _simple_name(text)
    return any(candidate and candidate in simple_text for candidate in candidates)


def _wait_for_matching_windows(gw, predicate, timeout: float = 1.0) -> list[str]:
    """Allow asynchronous GUI close requests a short bounded settle period."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = [
            (getattr(window, "title", "") or "").strip()
            for window in gw.getAllWindows()
            if predicate(window)
        ]
        if not remaining or time.monotonic() >= deadline:
            return remaining
        time.sleep(0.05)


def _wait_for_app_window(gw, candidates: list[str], timeout: float = 3.0):
    """Wait briefly for a newly launched app to publish its first window."""
    deadline = time.monotonic() + timeout
    while True:
        for window in gw.getAllWindows():
            title = (getattr(window, "title", "") or "").strip()
            if title and _text_matches_any(title, candidates):
                return window
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


def _wait_for_active_window(gw, target, timeout: float = 1.0) -> bool:
    """Verify that the requested target became the foreground window."""
    target_hwnd = getattr(target, "_hWnd", None)
    target_title = (getattr(target, "title", "") or "").strip()
    deadline = time.monotonic() + timeout
    while True:
        active = gw.getActiveWindow()
        if active is not None:
            active_hwnd = getattr(active, "_hWnd", None)
            active_title = (getattr(active, "title", "") or "").strip()
            if (
                target_hwnd
                and active_hwnd
                and target_hwnd == active_hwnd
            ) or (
                target_title
                and active_title == target_title
            ):
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def open_app(app_name: str) -> str:
    """
    Opens any application by name on Windows. Supports 60+ apps including WhatsApp,
    Telegram, Chrome, Spotify, VS Code, Discord, YouTube, Gmail, and more.
    Args:
        app_name (str): The name of the application to open (e.g. 'WhatsApp', 'Chrome', 'YouTube').
    """
    if not _is_safe_app_query(app_name):
        return "ERROR: Application name contains unsupported control characters or a path."

    name_clean = _normalize_app_query(app_name)
    if not name_clean:
        return "ERROR: Application name cannot be empty."

    match_res = _best_registry_match(name_clean)
    
    if match_res:
        matched_key, score = match_res
        logger.info(f"Fuzzy matched app name '{app_name}' to registry key '{matched_key}' (score: {score:.1f})")
        info = _resolve_alias(matched_key)
        actual_name = matched_key
    else:
        info = {}
        actual_name = name_clean
    
    # Strategy 1: URL (web apps)
    if "url" in info:
        import webbrowser
        webbrowser.open(info["url"])
        return f"SUCCESS: Opened {actual_name} in browser."
    
    # Strategy 2: Protocol URI
    if "protocol" in info:
        if _launch_protocol(info["protocol"]):
            return f"SUCCESS: Launched {actual_name} via protocol."
    
    # Strategy 3: Known path
    if "paths" in info:
        for path in info["paths"]:
            if _launch_existing_path(path):
                return f"SUCCESS: Launched {actual_name} from {path}."
    
    # Strategy 4: Shell exe (in PATH)
    if "exe" in info:
        if _launch_exe(info["exe"]):
            return f"SUCCESS: Launched {actual_name}."
    
    # Strategy 5: Windows Start Apps and Start menu shortcuts
    start_app_result = _launch_start_app(actual_name, info.get("ms_store", ""))
    if start_app_result:
        return start_app_result

    shortcut_result = _launch_start_menu_shortcut(actual_name, info.get("ms_store", ""))
    if shortcut_result:
        return shortcut_result

    if "url_fallback" in info:
        import webbrowser

        webbrowser.open(info["url_fallback"])
        return f"SUCCESS: Opened {actual_name} in browser fallback."

    return _launch_via_windows_search(actual_name)


def _is_system_process(proc) -> bool:
    import psutil
    try:
        parent = proc.parent()
        if parent and parent.pid == 4:
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    try:
        username = proc.username()
        if username in ("SYSTEM", "NT AUTHORITY\\SYSTEM"):
            return True
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    return False


def _process_name(proc) -> str:
    info = getattr(proc, "info", None)
    if isinstance(info, dict):
        name = info.get("name") or ""
    else:
        name = proc.name()
    return _simple_name(str(name).replace(".exe", ""))


@lru_cache(maxsize=1)
def _protected_runtime_pids() -> frozenset[int]:
    """Protect the active Maya/Codex host process tree, excluding Explorer."""
    import psutil

    try:
        current = psutil.Process(os.getpid())
        chain = [current]
        for parent in current.parents():
            try:
                if _process_name(parent) == "explorer":
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            chain.append(parent)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return frozenset({os.getpid()})

    protected = {proc.pid for proc in chain}
    host_anchor = None
    for proc in chain:
        try:
            if _process_name(proc) in _PROTECTED_HOST_PROCESS_NAMES:
                host_anchor = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if host_anchor is not None:
        try:
            protected.update(child.pid for child in host_anchor.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return frozenset(protected)


def _is_protected_runtime_process(proc) -> bool:
    """Protect Maya's current runtime chain and common host executables."""
    import psutil

    try:
        if proc.pid in _protected_runtime_pids():
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return True

    try:
        return _process_name(proc) in _PROTECTED_RUNTIME_PROCESS_NAMES
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return True


def _window_is_protected_runtime(window) -> bool:
    """Return True for Maya windows and windows owned by the active host tree."""
    title = (getattr(window, "title", "") or "").strip()
    simple_title = _simple_name(title)
    if (
        simple_title in _BULK_CLOSE_PROTECTED_TITLES
        or "maya ai" in simple_title
    ):
        return True

    hwnd = getattr(window, "_hWnd", None)
    if os.name != "nt" or not hwnd:
        return False

    try:
        import win32process

        owner_pid = int(win32process.GetWindowThreadProcessId(hwnd)[1])
        return owner_pid in _protected_runtime_pids()
    except Exception as exc:
        logger.debug(f"Could not inspect owner for window {title!r}: {exc}")
        return False


def _wait_for_process_exit(proc, timeout: float = 1.0) -> bool:
    """Confirm that a terminate/taskkill request actually removed the process."""
    import psutil

    try:
        proc.wait(timeout=timeout)
        return True
    except psutil.NoSuchProcess:
        return True
    except (psutil.TimeoutExpired, psutil.AccessDenied):
        return False
    except AttributeError:
        pid = getattr(proc, "pid", None)
        if not pid:
            return False
        deadline = time.monotonic() + timeout
        while psutil.pid_exists(pid):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
        return True


def close_app(app_name: str) -> str:
    """
    Closes a running application by name.
    Args:
        app_name (str): Name of the application to close (e.g. 'Chrome', 'Notepad').
    """
    import psutil

    if not _is_safe_app_query(app_name):
        return "ERROR: Application name contains unsupported control characters or a path."

    normalized = _normalize_app_query(app_name) or _simple_name(app_name)
    if normalized in _PROTECTED_APP_NAMES:
        return "ERROR: Maya AI is protected and cannot close itself."

    candidates = _app_name_candidates(app_name)
    closed = []
    failures = []
    protected_windows = []

    # Prefer closing visible windows first. This handles Store apps and web-app tabs
    # whose process name may be ApplicationFrameHost.exe or chrome.exe.
    try:
        import pygetwindow as gw

        for window in gw.getAllWindows():
            title = window.title or ""
            if not title or not _text_matches_any(title, candidates):
                continue
            if _window_is_protected_runtime(window):
                protected_windows.append(title)
                continue
            try:
                window.close()
                closed.append(title)
            except Exception as e:
                failures.append(f"{title}: {e}")
    except Exception as e:
        logger.debug(f"Window close lookup failed for {app_name}: {e}")

    if closed:
        # pygetwindow.close() only requests a close.  Do not claim completion
        # while a matching window is still present (common with unsaved apps).
        try:
            remaining = _wait_for_matching_windows(
                gw,
                lambda window: bool(
                    (getattr(window, "title", "") or "")
                    and _text_matches_any(window.title, candidates)
                    and not _window_is_protected_runtime(window)
                ),
            )
            if remaining:
                return (
                    f"PARTIAL: Requested close for {', '.join(closed[:5])}, "
                    f"but {len(remaining)} matching window(s) remain open."
                )
        except Exception as e:
            logger.debug(f"Window close verification failed for {app_name}: {e}")
            return f"PARTIAL: Requested close for {', '.join(closed[:5])}, but completion could not be verified."
        if protected_windows:
            return (
                f"PARTIAL: Closed window(s): {', '.join(closed[:5])}, but "
                f"{len(protected_windows)} protected Maya/runtime window(s) were kept open."
            )
        return f"SUCCESS: Closed window(s): {', '.join(closed[:5])}."

    killed = []
    system_skipped = False
    for proc in psutil.process_iter(["pid", "name"]):
        pname = proc.info.get("name") or ""
        pname_simple = _simple_name(pname.replace(".exe", ""))
        if not pname_simple:
            continue
        if not any(candidate and (candidate in pname_simple or pname_simple in candidate) for candidate in candidates):
            continue

        # Skip system-owned processes to avoid Access Denied errors on protected processes
        if _is_system_process(proc) or _is_protected_runtime_process(proc):
            system_skipped = True
            logger.debug(f"Skipping system process {pname} (PID {proc.pid})")
            continue

        terminate_error = None
        try:
            proc.terminate()
            if _wait_for_process_exit(proc):
                killed.append(pname)
                continue
            terminate_error = (
                f"{pname or proc.pid}: still running after terminate request"
            )
        except psutil.NoSuchProcess:
            killed.append(pname or f"PID {proc.pid}")
            continue
        except psutil.AccessDenied as e:
            terminate_error = f"{pname or proc.pid}: {e}"
        except Exception as e:
            terminate_error = f"{pname or proc.pid}: {e}"

        if os.name == "nt":
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    **_subprocess_kwargs(),
                )
                if result.returncode == 0:
                    if _wait_for_process_exit(proc):
                        killed.append(pname or f"PID {proc.pid}")
                        continue
                    failures.append(
                        f"{pname or proc.pid}: still running after forced close"
                    )
                elif result.stderr.strip():
                    failures.append(result.stderr.strip())
                elif terminate_error:
                    failures.append(terminate_error)
            except Exception as e:
                failures.append(f"taskkill {proc.pid}: {e}")
        elif terminate_error:
            failures.append(terminate_error)

    if killed and (failures or protected_windows or system_skipped):
        return (
            f"PARTIAL: Closed {', '.join(killed[:8])}, but "
            "one or more matching protected/failed targets remain."
        )
    if killed:
        return f"SUCCESS: Closed {', '.join(killed[:8])}."

    if (protected_windows or system_skipped) and not failures:
        return (
            f"ERROR: Refused to close {app_name} because it belongs to a "
            "protected Maya/runtime process."
        )

    if failures:
        return f"ERROR: Could not close {app_name}: {'; '.join(failures[:3])}"
    return f"No open window or process found matching '{app_name}'."


def close_apps_except(excluded_apps: str) -> str:
    """Close every titled app window except the named app(s).

    Args:
        excluded_apps (str): App names to keep open, separated by commas or
            ``and`` (for example, ``"VS Code"`` or ``"VS Code, Chrome"``).

    This deliberately closes windows instead of killing processes. It covers
    regular and minimized app windows while leaving background and system
    processes alone.

    An empty ``excluded_apps`` means "close every non-protected app" — a plain
    "close all apps" request. Maya/runtime host windows are still always kept
    open regardless.
    """
    # Empty string is the legitimate "close everything" request; only reject it
    # when it actually carries unsafe shell/path characters.
    if excluded_apps and not _is_safe_app_query(excluded_apps):
        return "ERROR: Excluded app names contain unsupported control characters or a path."

    excluded_names = [
        part.strip()
        for part in re.split(r"\s*(?:,|\band\b|\bar\b|\bebong\b|ও|এবং)\s*", excluded_apps, flags=re.IGNORECASE)
        if part.strip()
    ]

    excluded_candidates = [
        candidate
        for name in excluded_names
        for candidate in _app_name_candidates(name)
    ]
    closed = []
    failures = []
    kept = []
    protected_kept = []

    try:
        import pygetwindow as gw

        windows = gw.getAllWindows()
    except Exception as e:
        return f"ERROR: Could not inspect open app windows: {e}"

    for window in windows:
        title = (getattr(window, "title", "") or "").strip()
        if not title:
            continue
        simple_title = _simple_name(title)
        if (
            simple_title in _BULK_CLOSE_PROTECTED_TITLES
            or _text_matches_any(title, excluded_candidates)
        ):
            kept.append(title)
            continue
        if _window_is_protected_runtime(window):
            protected_kept.append(title)
            continue
        try:
            window.close()
            closed.append(title)
        except Exception as e:
            failures.append(f"{title}: {e}")

    if closed:
        try:
            requested_titles = set(closed)
            remaining_titles = set(
                _wait_for_matching_windows(
                    gw,
                    lambda window: (
                        (getattr(window, "title", "") or "").strip()
                        in requested_titles
                    ),
                )
            )
            remaining = [title for title in closed if title in remaining_titles]
            if remaining:
                failures.extend(f"{title}: still open after close request" for title in remaining)
                closed = [title for title in closed if title not in remaining_titles]
        except Exception as e:
            return (
                f"PARTIAL: Requested close for {len(closed)} app window(s), "
                f"but completion could not be verified: {e}"
            )

    keep_label = ", ".join(excluded_names) if excluded_names else "nothing (all apps)"
    protected_note = (
        f" Protected Maya/runtime windows kept open: {len(protected_kept)}."
        if protected_kept
        else ""
    )
    if closed and failures:
        return (
            f"PARTIAL: Closed {len(closed)} app window(s): {', '.join(closed[:8])}. "
            f"Kept open: {keep_label}. Could not close {len(failures)} window(s)."
            f"{protected_note}"
        )
    if closed:
        return (
            f"SUCCESS: Closed {len(closed)} app window(s): {', '.join(closed[:8])}. "
            f"Kept open: {keep_label}.{protected_note}"
        )
    if failures:
        return f"ERROR: Could not close app windows: {'; '.join(failures[:3])}"
    if kept:
        return (
            f"SUCCESS: No other app windows were open. Kept open: {keep_label}."
            f"{protected_note}"
        )
    return (
        f"SUCCESS: No open app windows were found. Kept open: {keep_label}."
        f"{protected_note}"
    )


def close_active_window() -> str:
    """Closes the currently active foreground window."""
    try:
        import pygetwindow as gw

        window = gw.getActiveWindow()
        if not window or not window.title:
            return "ERROR: No active window found."
        title = window.title
        if _window_is_protected_runtime(window):
            return f"ERROR: The active window '{title}' is protected and cannot be closed."
        window.close()
        remaining = _wait_for_matching_windows(
            gw,
            lambda item: (getattr(item, "title", "") or "").strip() == title,
        )
        if remaining:
            return f"PARTIAL: Requested close for active window '{title}', but it remains open."
        return f"SUCCESS: Closed active window: {title}."
    except Exception as e:
        return f"ERROR: Could not close active window: {e}"


def focus_app(app_name: str) -> str:
    """
    Brings a running application to the foreground and focuses it.
    Args:
        app_name (str): Name of the window/app to focus (e.g. 'WhatsApp', 'Chrome').
    """
    if not _is_safe_app_query(app_name):
        return "ERROR: Application name contains unsupported control characters or a path."

    try:
        import pygetwindow as gw

        candidates = _app_name_candidates(app_name)
        window = _wait_for_app_window(gw, candidates)
        if window is None:
            return f"No open window found matching '{app_name}'."
        if window.isMinimized:
            window.restore()
        window.activate()
        if not _wait_for_active_window(gw, window):
            return (
                f"PARTIAL: Requested focus for window '{window.title}', "
                "but it did not become the active window."
            )
        return f"SUCCESS: Focused window '{window.title}'."
    except Exception as e:
        return f"ERROR: Could not focus {app_name}: {e}"


def list_open_apps() -> str:
    """
    Lists all currently open applications (windows with visible titles).
    Useful to check what apps are running before switching to them.
    """
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        visible = [w.title for w in windows if w.title and not w.isMinimized]
        if visible:
            return "Open apps:\n" + "\n".join(f"  - {t}" for t in visible[:30])
        return "No visible windows found."
    except Exception as e:
        return f"ERROR: {e}"


def open_chrome_profile(profile_name: str) -> str:
    """
    Opens Google Chrome directly with a specific user profile — NO mouse, NO profile picker screen.
    Reads Chrome's Local State file to find the correct profile folder, then launches Chrome
    with --profile-directory flag so the profile picker screen never appears.

    Args:
        profile_name (str): The display name of the Chrome profile to open.
                           Examples: 'Nirupam', 'Ankita', 'Som', 'Default', 'Guest'

    Returns: SUCCESS or ERROR string.
    """
    import json

    # ── Step 1: Find Chrome executable ───────────────────────────────────────
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    chrome_exe = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome_exe = p
            break
    if not chrome_exe:
        return "ERROR: Chrome executable not found."

    # ── Step 2: Read Chrome's Local State to find profiles ───────────────────
    local_state_path = os.path.expandvars(
        r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State"
    )
    if not os.path.exists(local_state_path):
        return "ERROR: Chrome Local State file not found. Is Chrome installed?"

    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        profiles_info = local_state.get("profile", {}).get("info_cache", {})
    except Exception as e:
        return f"ERROR: Could not read Chrome profiles: {e}"

    if not profiles_info:
        return "ERROR: No Chrome profiles found."

    # ── Step 3: Fuzzy match profile name ─────────────────────────────────────
    name_clean = profile_name.strip().lower()

    # Build match candidates: folder → display name
    candidates = {}
    for folder, info in profiles_info.items():
        display = info.get("name", "").strip()
        email   = info.get("user_name", "").strip()
        candidates[folder] = {"name": display, "email": email}

    # Try exact match first
    matched_folder = None
    matched_name   = None
    for folder, info in candidates.items():
        if info["name"].lower() == name_clean:
            matched_folder = folder
            matched_name   = info["name"]
            break

    # Fuzzy match if no exact match
    if not matched_folder:
        try:
            from rapidfuzz import process, fuzz
            all_names = {folder: info["name"] for folder, info in candidates.items()}
            result = process.extractOne(
                name_clean,
                all_names,
                scorer=fuzz.partial_ratio,
                score_cutoff=60,
                processor=str.lower,
            )
            if result:
                matched_name, score, matched_folder = result
                logger.info(f"Chrome profile fuzzy match: '{profile_name}' → '{matched_name}' (folder: {matched_folder}, score: {score:.0f})")
        except ImportError:
            pass

    if not matched_folder:
        # List available profiles in error message
        available = ", ".join(f"'{i['name']}'" for i in candidates.values())
        return (
            f"ERROR: No Chrome profile matching '{profile_name}' found.\n"
            f"Available profiles: {available}"
        )

    # ── Step 4: Launch Chrome with profile flag (NO mouse, NO picker!) ────────
    try:
        cmd = [chrome_exe, f"--profile-directory={matched_folder}"]
        subprocess.Popen(cmd)
        logger.info(f"Chrome launched with profile '{matched_name}' (folder: {matched_folder})")
        return (
            f"SUCCESS: Chrome opened with profile '{matched_name}'.\n"
            f"Profile folder: {matched_folder}"
        )
    except Exception as e:
        return f"ERROR: Failed to launch Chrome with profile '{matched_name}': {e}"
