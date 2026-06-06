"""
Maya AI — Smart App Launcher
Opens Windows applications intelligently using multiple strategies.
"""
import os
import subprocess
import time
import logging

logger = logging.getLogger(__name__)

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
    "whatsapp": {"protocol": "whatsapp://", "ms_store": "WhatsApp"},
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
    if "alias" in info:
        return APP_REGISTRY.get(info["alias"], {})
    return info


def open_app(app_name: str) -> str:
    """
    Opens any application by name on Windows. Supports 60+ apps including WhatsApp,
    Telegram, Chrome, Spotify, VS Code, Discord, YouTube, Gmail, and more.
    Args:
        app_name (str): The name of the application to open (e.g. 'WhatsApp', 'Chrome', 'YouTube').
    """
    from rapidfuzz import process, fuzz
    
    name_clean = app_name.strip().lower()
    if not name_clean:
        return "ERROR: Application name cannot be empty."
        
    registry_keys = list(APP_REGISTRY.keys())
    
    # Fuzzy match the input app name with the registry keys
    match_res = process.extractOne(
        name_clean,
        registry_keys,
        scorer=fuzz.partial_ratio,
        score_cutoff=80.0
    )
    
    if match_res:
        matched_key, score, _ = match_res
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
        try:
            os.startfile(info["protocol"])
            return f"SUCCESS: Launched {actual_name} via protocol."
        except Exception as e:
            logger.warning(f"Protocol launch failed for {actual_name}: {e}")
    
    # Strategy 3: Known path
    if "paths" in info:
        for path in info["paths"]:
            if os.path.exists(path):
                try:
                    subprocess.Popen(path, shell=info.get("shell", False))
                    return f"SUCCESS: Launched {actual_name} from {path}."
                except Exception as e:
                    logger.warning(f"Path launch failed: {e}")
    
    # Strategy 4: Shell exe (in PATH)
    if "exe" in info:
        try:
            subprocess.Popen(info["exe"], shell=info.get("shell", True))
            return f"SUCCESS: Launched {actual_name}."
        except Exception as e:
            logger.warning(f"EXE launch failed for {info['exe']}: {e}")
    
    # Strategy 5: Generic fallback — try os.startfile and then Win+S search
    try:
        subprocess.Popen(f'start "" "{actual_name}"', shell=True)
        time.sleep(0.5)
        return f"SUCCESS: Attempted to open {actual_name} via Windows Start."
    except Exception:
        pass
    
    # Strategy 6: Windows Search via pyautogui
    try:
        import pyautogui
        pyautogui.press("win")
        time.sleep(0.7)
        pyautogui.write(actual_name, interval=0.04)
        time.sleep(0.9)
        pyautogui.press("enter")
        return f"SUCCESS: Searched and opened {actual_name} via Windows Search."
    except Exception as e:
        return f"ERROR: Could not open {actual_name}. {e}"


def close_app(app_name: str) -> str:
    """
    Closes a running application by name.
    Args:
        app_name (str): Name of the application to close (e.g. 'Chrome', 'Notepad').
    """
    import psutil
    name_lower = app_name.lower().strip()
    killed = []
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            pname = (proc.info["name"] or "").lower()
            if name_lower in pname or pname.replace(".exe", "") in name_lower:
                proc.kill()
                killed.append(proc.info["name"])
        if killed:
            return f"SUCCESS: Closed {', '.join(killed)}."
        return f"No process found matching '{app_name}'."
    except Exception as e:
        return f"ERROR: Could not close {app_name}: {e}"


def focus_app(app_name: str) -> str:
    """
    Brings a running application to the foreground and focuses it.
    Args:
        app_name (str): Name of the window/app to focus (e.g. 'WhatsApp', 'Chrome').
    """
    import pygetwindow as gw
    name_lower = app_name.lower().strip()
    try:
        windows = gw.getAllWindows()
        for w in windows:
            if name_lower in w.title.lower():
                if w.isMinimized:
                    w.restore()
                w.activate()
                return f"SUCCESS: Focused window '{w.title}'."
        return f"No open window found matching '{app_name}'."
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

