import os
import subprocess
import psutil
import pyperclip

def get_active_windows() -> str:
    """
    Returns a list of titles of currently visible windows.
    Useful for seeing what applications the user is currently running.
    """
    try:
        cmd = 'powershell "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object Name, MainWindowTitle"'
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        return f"Active Windows:\n{result.stdout}"
    except Exception as e:
        return f"ERROR: Could not get active windows. {e}"

def change_volume(level: int) -> str:
    """
    Changes the system volume to the specified level (0-100).
    Requires Windows.
    """
    if not (0 <= level <= 100):
        return "ERROR: Volume level must be between 0 and 100."
        
    scalar_level = float(level) / 100.0
    
    ps_code_template = r'''
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {
    int f(); int g(); int h(); int i();
    int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
    int j();
    int GetMasterVolumeLevelScalar(out float pfLevel);
    int k(); int l(); int m(); int n();
    int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid pguidEventContext);
    int GetMute(out bool pbMute);
}

[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
    int Activate(ref Guid id, int clsCtx, int activationParams, out IAudioEndpointVolume aev);
}

[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
    int f();
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
}

[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class MMDeviceEnumeratorComObject { }

public class Audio {
    static IAudioEndpointVolume Vol() {
        var enumerator = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator;
        IMMDevice dev = null;
        enumerator.GetDefaultAudioEndpoint(0, 1, out dev);
        IAudioEndpointVolume epv = null;
        var epvid = typeof(IAudioEndpointVolume).GUID;
        dev.Activate(ref epvid, 23, 0, out epv);
        return epv;
    }
    public static float Volume {
        get { float v = -1; Vol().GetMasterVolumeLevelScalar(out v); return v; }
        set { Vol().SetMasterVolumeLevelScalar(value, Guid.Empty); }
    }
}
'@
[Audio]::Volume = {scalar_level}
'''
    ps_code = ps_code_template.replace("{scalar_level}", str(scalar_level))
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-Command", ps_code],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return f"SUCCESS: Changed system volume to {level}%."
        else:
            return f"ERROR: Failed to set volume: {result.stderr}"
    except Exception as e:
        return f"ERROR executing volume command: {e}"

def read_clipboard() -> str:
    """Returns the current text content of the system clipboard."""
    try:
        return pyperclip.paste()
    except Exception as e:
        return f"ERROR reading clipboard: {e}"

def write_clipboard(text: str) -> str:
    """Writes the specified text to the system clipboard."""
    try:
        pyperclip.copy(text)
        return "SUCCESS: Text copied to clipboard."
    except Exception as e:
        return f"ERROR writing to clipboard: {e}"

def get_system_stats() -> str:
    """Returns current CPU, Memory, and Disk usage statistics."""
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return f"CPU Usage: {cpu}%\nMemory Usage: {mem.percent}% ({mem.used / (1024**3):.2f}GB / {mem.total / (1024**3):.2f}GB)\nDisk Usage: {disk.percent}%"
    except Exception as e:
        return f"ERROR getting system stats: {e}"

def manage_processes(action: str, pid: int = None, process_name: str = None) -> str:
    """
    Kill or manage a process by PID or Name.
    Args:
        action (str): Must be 'kill'.
        pid (int, optional): The Process ID to kill.
        process_name (str, optional): The name of the process to kill (e.g., 'notepad.exe').
    """
    if action != "kill":
        return "ERROR: Unsupported action. Only 'kill' is supported."

    # The legacy tool shares the unified route so it cannot bypass protected
    # target checks or claim success before the target has actually exited.
    from backend.tools.unified.handlers.system_ops import handle_pc

    return handle_pc("process_kill", val=pid or 0, name=process_name or "")

def read_on_screen_text() -> str:
    """
    Captures the current screen and runs OCR to extract all visible text.
    Useful for reading error messages, UI labels, or content not accessible via clipboard.
    """
    try:
        from ...vision.capture.screen_capture import screen_capture
        from ...vision.ocr.ocr_engine import ocr_engine
        import time
        
        img, monitor = screen_capture.capture_as_pil()
        if not img:
            return "ERROR: Could not capture screen (possibly sensitive app blocking)."
            
        processed_img = ocr_engine.preprocess_image(img)
        
        # We need to extract raw text, not just coordinates.
        if not ocr_engine.reader:
            return "ERROR: OCR engine not initialized."
            
        t0 = time.time()
        results = ocr_engine.reader.readtext(processed_img)
        t_ocr = time.time()
        
        texts = []
        for (bbox, text, conf) in results:
            if conf >= 0.2:
                texts.append(text)
                
        if not texts:
            return "No readable text found on screen."
            
        return f"Visible Text (Confidence > 0.2):\n" + " ".join(texts)
    except Exception as e:
        return f"ERROR running OCR: {e}"

def _launch_whatsapp_desktop(timeout_seconds: float = 10.0) -> str:
    """Launch the real WhatsApp Desktop app by any available means."""
    import subprocess
    import shutil
    import json

    # 1. Try Windows Start Apps (Microsoft Store / installed UWP/PWA)
    try:
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell:
            cmd = (
                "Get-StartApps | Where-Object { $_.Name -like '*WhatsApp*' } "
                "| Select-Object Name, AppID | ConvertTo-Json -Compress"
            )
            result = subprocess.run(
                [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True, text=True, timeout=8,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    appid = str(item.get("AppID") or "").strip()
                    if appid:
                        try:
                            subprocess.Popen(
                                ["explorer.exe", f"shell:AppsFolder\\{appid}"],
                                shell=False,
                            )
                            return "START_APPS"
                        except Exception:
                            pass
    except Exception:
        pass

    # 2. Try Start menu shortcuts
    try:
        from pathlib import Path
        roots = [
            os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
        ]
        for root in roots:
            for child in Path(root).rglob("*"):
                if child.suffix.lower() in {".lnk", ".url"} and "whatsapp" in child.stem.lower():
                    try:
                        os.startfile(str(child))
                        return "START_MENU"
                    except Exception:
                        pass
    except Exception:
        pass

    # 3. Try known executable locations
    known_paths = [
        os.path.expandvars(r"%LocalAppData%\WhatsApp\WhatsApp.exe"),
        os.path.expandvars(r"%ProgramFiles%\WhatsApp\WhatsApp.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\WhatsApp\WhatsApp.exe"),
    ]
    for p in known_paths:
        if os.path.exists(p):
            try:
                subprocess.Popen([p], shell=False)
                return "EXE"
            except Exception:
                pass

    # 4. Protocol URI as last resort (often opens Store/Desktop app)
    try:
        os.startfile("whatsapp://")
        return "PROTOCOL"
    except Exception:
        pass

    return "FAILED"


def _open_and_focus_whatsapp(timeout_seconds: float = 12.0):
    """Helper: Open or focus the WhatsApp Desktop window. Returns gw.Win32Window."""
    import pygetwindow as gw
    import time

    # Try finding an existing WhatsApp window first
    for title_kw in ["WhatsApp", "whatsapp"]:
        windows = gw.getWindowsWithTitle(title_kw)
        if windows:
            win = windows[0]
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
            except Exception:
                pass
            time.sleep(0.6)
            return win

    # Launch WhatsApp Desktop directly (avoid browser fallback)
    launch_method = _launch_whatsapp_desktop(timeout_seconds)
    if launch_method == "FAILED":
        raise RuntimeError("Could not launch WhatsApp Desktop by any method.")

    # Wait for the window to appear
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        time.sleep(0.6)
        windows = gw.getWindowsWithTitle("WhatsApp")
        if windows:
            win = windows[0]
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
            except Exception:
                pass
            time.sleep(0.5)
            return win

    raise RuntimeError(f"Could not open WhatsApp window after {timeout_seconds}s.")


def _whatsapp_navigate_to_contact(contact_name: str) -> str:
    """Helper: Focus WhatsApp search, type the contact name, and open the chat."""
    import pyautogui
    import time

    # WhatsApp Desktop search shortcuts: Ctrl+E (newer) or Ctrl+F (older).
    # We try Ctrl+E first.
    for shortcut in [("ctrl", "e"), ("ctrl", "f")]:
        pyautogui.hotkey(*shortcut)
        time.sleep(0.4)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        pyautogui.write(contact_name, interval=0.04)
        time.sleep(1.2)  # Wait for search results to populate

        # Open first result: Down then Enter.
        pyautogui.press("down")
        time.sleep(0.25)
        pyautogui.press("enter")
        time.sleep(1.0)

        # If we can find the message input placeholder, chat opened.
        from backend.vision.capture.screen_capture import screen_capture
        from backend.vision.ocr.ocr_engine import ocr_engine
        try:
            img, _ = screen_capture.capture_as_pil()
            if img:
                processed = ocr_engine.preprocess_image(img)
                for hint in ["Type a message", "Search", "Type a message", "Start a conversation"]:
                    coords = ocr_engine.find_text_coordinates(processed, hint, fuzzy_threshold=0.65)
                    if coords:
                        return "SUCCESS: Chat opened."
        except Exception:
            pass

    # Fall back to OCR click on the contact name if visible.
    from backend.tools.desktop.advanced.vision_tools import find_and_click
    result = find_and_click(contact_name, timeout=3.0)
    if result.startswith("SUCCESS"):
        return "SUCCESS: Chat opened via click."
    return f"ERROR: Could not open chat for '{contact_name}'."


def _whatsapp_type_and_send(message: str) -> str:
    """Helper: Type a message into the active WhatsApp chat and send it."""
    import pyautogui
    import time

    # The message input should already be focused after selecting a chat.
    # Just type and press Enter.
    pyautogui.write(message, interval=0.03)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.8)
    return "SUCCESS: Message sent."


def whatsapp_ui_send_message(contact_name: str, message: str) -> str:
    """
    Opens the WhatsApp Desktop app, finds the contact by name, types the message,
    and sends it via the UI. Use this when the user explicitly asks to
    "open WhatsApp and find X and send".

    Args:
        contact_name (str): The contact name to search for in WhatsApp.
        message (str): The text message to send.
    """
    try:
        _open_and_focus_whatsapp()
    except Exception as e:
        return f"ERROR: Could not open WhatsApp Desktop: {e}"

    nav_result = _whatsapp_navigate_to_contact(contact_name)
    if nav_result.startswith("ERROR"):
        return nav_result

    try:
        return _whatsapp_type_and_send(message)
    except Exception as e:
        return f"ERROR: Could not send message in WhatsApp UI: {e}"


def whatsapp_call(contact_name: str) -> str:
    """
    Initiates a WhatsApp call. Note: calling is disabled/unsupported in the Baileys background service.
    Args:
        contact_name (str): The name of the contact to call.
    """
    return f"ERROR: WhatsApp voice or video calling is not supported via the background service. Please send a text message instead to '{contact_name}'."

def read_whatsapp_chat(contact_name_or_phone: str, limit: int = 10) -> str:
    """
    Reads the most recent WhatsApp messages from a specific contact.
    Use this to read chat history or check if someone sent a new message.
    Args:
        contact_name_or_phone (str): The exact phone number OR the name of the contact.
        limit (int): Number of recent messages to fetch (default is 10).
    Returns:
        str: A formatted string of recent messages with ISO timestamps and sender names.
    """
    from backend.tools.desktop.advanced.contacts import lookup_contact
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
    
    # Try fuzzy matching first if it does not look like a raw number
    phone = contact_name_or_phone.strip()
    clean_digits = phone.replace('+', '').replace(' ', '').replace('-', '')
    
    if not clean_digits.isdigit():
        match = lookup_contact(contact_name_or_phone)
        if match:
            phone = match["phone"]
        else:
            return f"ERROR: Contact '{contact_name_or_phone}' not found in database and is not a valid phone number."
            
    # Check status
    status = whatsapp_manager.get_status()
    if status.get("status") not in ["connected", "authenticated"]:
        if status.get("hasQr"):
            return f"ERROR: WhatsApp is not connected. A pairing QR code has been generated. Please scan the QR code to connect."
        return f"ERROR: WhatsApp is not connected (status: {status.get('status')})."

    # Fetch messages
    result = whatsapp_manager.fetch_messages(phone, limit=limit)
    if not result.get("success"):
        return f"ERROR fetching messages: {result.get('error', 'Unknown error')}"
        
    data = result.get("data", [])
    if not data:
        return f"No recent messages found with '{contact_name_or_phone}'."
        
    formatted = []
    for msg in data:
        sender = "You" if msg.get("fromMe") else msg.get("senderName", contact_name_or_phone)
        body = msg.get("body", "<Media/Unsupported>")
        time_iso = msg.get("timestampISO", "")
        # Extract time for readability HH:MM
        try:
            time_str = time_iso.split('T')[1][:5]
        except Exception:
            time_str = ""
        formatted.append(f"{sender} ({time_str}): {body}")
        
    return "\n".join(formatted)

def _contact_not_found_reply(contact_name: str, error: str) -> str:
    """Deterministic reply payload when a WhatsApp contact can't be resolved.

    Returns a CLARIFICATION_NEEDED JSON payload; agent_team renders it in the
    user's own language (bn/hi/en) and relays it verbatim — the LLM never
    paraphrases it (weak fallback models leak instructions when they do).
    """
    import json as _json
    reason = "not_connected" if "not connected" in (error or "").lower() else "not_found"
    payload = _json.dumps(
        {"kind": "contact_not_found", "name": contact_name, "reason": reason},
        ensure_ascii=False,
    )
    return f"CLARIFICATION_NEEDED:{payload}"


def _contact_pick_reply(contact_name: str, candidates: list) -> str:
    import json as _json

    payload = _json.dumps(
        {
            "kind": "contact_pick",
            "query": contact_name,
            "candidates": [
                {"name": c.get("name", "?"), "number": c.get("number", "?")}
                for c in candidates
            ],
        },
        ensure_ascii=False,
    )
    return f"CLARIFICATION_NEEDED:{payload}"


def whatsapp_send_message(contact_name: str, message: str) -> str:
    """
    Sends a WhatsApp message to a contact by name (no UI, no mouse).
    Resolution order:
      1. Maya's saved contacts database
      2. WhatsApp's synced contacts searched by name
      3. If only one match found → send immediately.
      4. If multiple matches found → return the list and ask user to clarify.
      5. If none found → honest error.
    Args:
        contact_name (str): The name of the contact (e.g. 'Anup') or a phone number.
        message (str): The text message to send.
    """
    from backend.tools.desktop.advanced.contacts import lookup_contact
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
    import re

    # 1. Raw phone number
    if re.fullmatch(r'[\d\s\-\+]{7,15}', contact_name.strip()):
        phone = whatsapp_manager._normalize_phone(contact_name)
        if not phone:
            return "ERROR: Invalid WhatsApp phone number."

        receipt = whatsapp_manager.send_message_receipt(phone, message)
        if receipt.get("success"):
            return f"SUCCESS: WhatsApp accepted the message for '{contact_name}' ({phone}). Delivery: {receipt.get('status', 'sent').title()}."
        return f"ERROR: WhatsApp did not send the message to '{contact_name}': {receipt.get('error', 'unknown error')}"

    # 2. Try Maya contact DB
    match = lookup_contact(contact_name)
    if match:
        candidates = [{"name": match["name"], "number": match["phone"]}]
    else:
        # 3. Search WhatsApp synced contacts by name
        resolved = whatsapp_manager.resolve_contact(contact_name)
        if not resolved.get("success"):
            return _contact_not_found_reply(contact_name, resolved.get("error", ""))
        candidates = resolved.get("candidates", [])
        if not candidates:
            candidates = [{"name": resolved.get("name", contact_name), "number": resolved.get("phone")}]

    if not candidates:
        return _contact_not_found_reply(contact_name, "")

    # 4. Multiple matches → ask user to pick (agent_team renders the list
    # in the user's language and relays it verbatim, bypassing the LLM)
    if len(candidates) > 1:
        import json as _json
        payload = _json.dumps(
            {
                "kind": "contact_pick",
                "query": contact_name,
                "candidates": [
                    {"name": c.get("name", "?"), "number": c.get("number", "?")}
                    for c in candidates
                ],
            },
            ensure_ascii=False,
        )
        return f"CLARIFICATION_NEEDED:{payload}"

    # 5. Single match → send
    best = candidates[0]
    display_name = best.get("name", contact_name)
    phone = whatsapp_manager._normalize_phone(best.get("number"))
    if not phone:
        return f"ERROR: Invalid phone number for '{display_name}'."

    receipt = whatsapp_manager.send_message_receipt(phone, message)
    if receipt.get("success"):
        return f"SUCCESS: WhatsApp accepted the message for '{display_name}' ({phone}). Delivery: {receipt.get('status', 'sent').title()}."
    return f"ERROR: WhatsApp did not send the message to '{display_name}': {receipt.get('error', 'unknown error')}"

def whatsapp_revoke_message(contact_name: str, count: int = 1) -> str:
    """
    Revokes (Deletes for Everyone) the most recent messages you sent to a contact.
    Args:
        contact_name (str): The name of the contact (e.g. 'Pintu') or phone number.
        count (int): The number of recent messages to delete (default 1).
    """
    from backend.tools.desktop.advanced.contacts import lookup_contact
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
    import re
    
    phone = None
    display_name = contact_name
    if re.fullmatch(r'[\d\s\-\+]{7,15}', contact_name.strip()):
        clean_num = re.sub(r'[^\d]', '', contact_name.strip())
        if len(clean_num) == 10:
            phone = "91" + clean_num
        elif len(clean_num) >= 11:
            phone = clean_num
    
    if phone is None:
        match = lookup_contact(contact_name)
        if not match:
            return f"ERROR: Contact '{contact_name}' not found in database."
        phone = match["phone"]
        display_name = match["name"]

    receipt = whatsapp_manager.revoke_messages_receipt(phone, count)
    if receipt.get("success"):
        return f"SUCCESS: WhatsApp accepted delete-for-everyone for {receipt['revoked']} message(s) sent to '{display_name}' ({phone})."
    return f"ERROR: WhatsApp could not delete messages for everyone for '{display_name}': {receipt.get('error', 'unknown error')}"

def whatsapp_get_pairing_code(phone: str) -> str:
    """
    Generates an 8-digit pairing code to link Maya AI with your WhatsApp account using your phone number.
    Args:
        phone (str): Your 10-digit phone number with or without country code (e.g. '9876543210' or '+919876543210').
    """
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
    
    clean_phone = "".join(c for c in phone if c.isdigit())
    if not clean_phone:
        return "ERROR: Invalid phone number format. Please provide a valid 10-digit phone number."
        
    if clean_phone.startswith("00"):
        clean_phone = clean_phone[2:]
    elif clean_phone.startswith("0"):
        clean_phone = clean_phone[1:]
        
    if len(clean_phone) == 10:
        clean_phone = "91" + clean_phone
        
    code = whatsapp_manager.get_pairing_code(clean_phone)
    if code:
        return f"SUCCESS: Generated WhatsApp pairing code: {code}\n\nTo link your account:\n1. Open WhatsApp on your phone.\n2. Go to Settings -> Linked Devices -> tap 'Link a Device'.\n3. Tap 'Link with phone number instead' at the bottom.\n4. Enter the 8-digit code: {code}"
    return "ERROR: Failed to generate pairing code. Please ensure your WhatsApp background service is active."

def pause_media() -> str:
    """
    Pauses or resumes playing media (music, videos, YouTube) on the system.
    """
    import pyautogui
    try:
        pyautogui.press('playpause')
        return "SUCCESS: Pressed media play/pause key."
    except Exception as e:
        return f"ERROR pausing media: {e}"

def setup_missing_tool(tool_name: str, download_url: str, install_args: str = None) -> str:
    """
    Downloads and installs a software or tool silently in the background.
    Args:
        tool_name (str): The name of the installer file to save (e.g. 'nodejs_installer.msi').
        download_url (str): The direct HTTPS URL to download the installer from.
        install_args (str, optional): Arguments for silent installation (e.g. '/quiet /norestart').

    Security hardening:
        - Only HTTPS URLs are accepted (no http://, file://, etc.)
        - tool_name is sanitised to a plain filename (no path traversal)
        - subprocess is called with shell=False and a pre-split argument list
          to prevent command injection via any parameter
    """
    import urllib.request
    import urllib.parse
    import tempfile
    import os
    import subprocess

    # ── 1. Validate URL — accept only HTTPS to prevent MITM/downgrade attacks ──
    try:
        parsed = urllib.parse.urlparse(download_url)
    except Exception:
        return "ERROR: Invalid download URL."
    if parsed.scheme.lower() != "https":
        return "ERROR: Only HTTPS download URLs are permitted for security reasons."

    # ── 2. Sanitise tool_name — strip all directory components ────────────────
    safe_name = os.path.basename(tool_name)
    # Reject empty names and names that changed after sanitisation (path traversal)
    if not safe_name or safe_name != tool_name:
        return "ERROR: Invalid tool name (path traversal characters detected)."
    # Only allow .msi and .exe installers
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in (".msi", ".exe"):
        return "ERROR: Only .msi and .exe installer files are supported."

    try:
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, safe_name)

        # ── 3. Download ───────────────────────────────────────────────────────
        urllib.request.urlretrieve(download_url, file_path)

        # ── 4. Execute installer with shell=False (no command injection) ──────
        if ext == ".msi":
            default_args = ["/quiet", "/norestart"]
            extra = install_args.split() if install_args else default_args
            cmd = ["msiexec", "/i", file_path] + extra
        else:  # .exe
            default_args = ["/silent", "/verysilent", "/norestart", "/sp-"]
            extra = install_args.split() if install_args else default_args
            cmd = [file_path] + extra

        subprocess.run(cmd, shell=False, check=True)
        return f"SUCCESS: Downloaded and silently installed {safe_name}."
    except subprocess.CalledProcessError as e:
        return f"ERROR: Installer exited with code {e.returncode}."
    except Exception as e:
        return f"ERROR setting up tool: {e}"



# ── WhatsApp File Sending ─────────────────────────────────────────────────────

# Directories Maya should NEVER search inside (project files, system cache)
_MAYA_PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

# Extensions considered user documents/media (higher priority than scripts)
_PREFERRED_EXTS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
    '.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.ogg',
    '.zip', '.rar', '.7z', '.tar', '.gz',
    '.txt', '.csv',
}

# Filler words that carry no filename signal — stripped from a fuzzy file query
# so a loose spoken description ("Aridam dada hostel issue pdf ta") still matches
# a file actually named e.g. "Hostel Issue Aridam.pdf".
_FILE_QUERY_STOPWORDS = {
    "ta", "tar", "the", "a", "an", "of", "er", "e", "o", "ei", "oi", "ke", "kori",
    "file", "files", "document", "documents", "doc", "please", "pls", "koro", "kore",
    "dao", "de", "send", "pathao", "pathiye", "patha", "attach", "attachment",
    "gmail", "mail", "email", "name", "naam", "wala", "walla",
}
# Bare extension words (no dot) → treated as an extension hint, not a name token.
_EXT_WORDS = {
    "pdf": ".pdf", "doc": ".doc", "docx": ".docx", "xls": ".xls", "xlsx": ".xlsx",
    "ppt": ".ppt", "pptx": ".pptx", "txt": ".txt", "csv": ".csv", "zip": ".zip",
    "jpg": ".jpg", "jpeg": ".jpeg", "png": ".png", "gif": ".gif", "webp": ".webp",
    "mp4": ".mp4", "mkv": ".mkv", "mp3": ".mp3", "wav": ".wav", "rar": ".rar",
}


def _parse_file_query(query: str):
    """Split a fuzzy file query into (tokens, ext_hint).

    - Detects the wanted extension either as a real suffix ('report.pdf') or a
      bare extension word anywhere in the phrase ('report pdf', 'hostel pdf ta').
    - Drops filler/stopwords + the extension word so a loose multi-word
      description still matches (order-independent token match downstream).
    """
    raw = (query or "").lower().strip()
    # A real suffix extension only counts when the LAST word ends in ".<alnum>"
    # (e.g. "report.pdf"). Never run splitext on the whole phrase — "project 2.1
    # pdf" would wrongly yield ext=".1 pdf" and then match no file at all.
    last_word = raw.split()[-1] if raw.split() else ""
    suffix = os.path.splitext(last_word)[1]
    ext = suffix if (1 < len(suffix) <= 6 and suffix[1:].isalnum()) else ""
    cleaned = "".join(c if c.isalnum() else " " for c in raw)
    tokens = []
    for w in cleaned.split():
        if w in _EXT_WORDS:
            ext = ext or _EXT_WORDS[w]   # bare extension word → ext hint
            continue
        if w in _FILE_QUERY_STOPWORDS or len(w) < 2:
            continue
        tokens.append(w)
    return tokens, ext


def _file_match_tier(fname: str, tokens: list, ext_hint: str):
    """Score how well ``fname`` matches a fuzzy query. Returns (tier, hits).

      tier 2 = every query token appears in the name (any order)  -> strong
      tier 1 = at least half the tokens appear (>=1)              -> partial
      tier 0 = no usable match / extension mismatch
    ``hits`` (token count) breaks ties within a tier so the closest name wins.
    """
    name_lower = fname.lower()
    if ext_hint and os.path.splitext(name_lower)[1] != ext_hint:
        return (0, 0)
    if not tokens:
        # Query was only an extension (e.g. "pdf") — any file of that ext matches.
        return (2, 0) if ext_hint else (0, 0)
    hits = sum(1 for t in tokens if t in name_lower)
    if hits == 0:
        return (0, 0)
    if hits == len(tokens):
        return (2, hits)
    threshold = max(1, (len(tokens) + 1) // 2)
    if hits >= threshold:
        return (1, hits)
    return (0, 0)


def _find_file_in_search_dirs(query: str, folder_hint: str = "") -> str | None:
    """
    Searches common folders across ALL available drives (C:, D:, etc.) for a file.
    Priority: preferred document/media types before scripts/code files.
    Excludes the Maya AI project directory to prevent returning internal files.
    
    Args:
        query: filename keyword to search for (e.g. 'PAY', 'syllabus.pdf')
        folder_hint: optional folder name hint (e.g. 'RRB', 'Documents')
    Returns the first matching absolute file path, or None if not found.
    """
    import os
    import string
    from backend.tools.desktop.advanced.whatsapp_manager import validate_attachment_path
    home = os.path.expanduser("~")

    # Heavy skip list — directories to never recurse into
    SKIP_DIRS = {
        'node_modules', '.git', '.venv', '__pycache__', '.cache',
        'windows', 'program files', 'program files (x86)', 'programdata',
        '$recycle.bin', 'system volume information', 'recovery',
        'appdata', '.gemini',
    }
    # Also skip the maya project directory — EXCEPT its data/uploads cache, where
    # files the user drags into Maya are stored and must remain findable.
    maya_dir_lower = _MAYA_PROJECT_DIR.lower()
    uploads_dir_lower = os.path.abspath("data/uploads").lower()

    folder_hint_lower = folder_hint.lower().strip() if folder_hint else ""
    # Token-based fuzzy parse so a loose multi-word description
    # ("Aridam dada hostel issue pdf ta") still matches "Hostel Issue Aridam.pdf".
    query_tokens, query_ext = _parse_file_query(query)

    # Build search dirs: start with the folder_hint if provided on all drives,
    # then standard home dirs, then all drive roots + immediate subdirs
    SEARCH_DIRS = []

    # If folder hint given, look for that folder on all drives first
    if folder_hint_lower:
        for drive_letter in string.ascii_uppercase:
            drive_root = f"{drive_letter}:\\"
            if os.path.exists(drive_root):
                try:
                    for item in os.listdir(drive_root):
                        if item.lower() == folder_hint_lower or folder_hint_lower in item.lower():
                            candidate = os.path.join(drive_root, item)
                            if os.path.isdir(candidate):
                                SEARCH_DIRS.append(candidate)
                except PermissionError:
                    pass

    # Standard home dirs
    SEARCH_DIRS += [
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "Desktop"),
        os.path.abspath("data/uploads"),
    ]

    # All drive roots and immediate subdirs (D:\ before C:\ so user data first)
    for drive_letter in list('DCEFGHIJKLMNOPQRSTUVWXYZA'):
        drive_root = f"{drive_letter}:\\"
        if os.path.exists(drive_root):
            SEARCH_DIRS.append(drive_root)
            try:
                for item in os.listdir(drive_root):
                    item_path = os.path.join(drive_root, item)
                    if os.path.isdir(item_path) and not item.startswith('.'):
                        SEARCH_DIRS.append(item_path)
            except PermissionError:
                pass

    # ── Deduplicate SEARCH_DIRS ───────────────────────────────────────────────
    # SEARCH_DIRS may contain both a drive root (e.g. D:\) and its immediate
    # subdirectories (e.g. D:\Users).  os.walk() is recursive, so walking D:\
    # already covers D:\Users — keeping both causes every subdir to be walked
    # twice, multiplying I/O time on large drives.
    # Solution: build the absolute set, then keep a path only if no OTHER path
    # in the full set is its ancestor.  This is order-independent, so home dirs
    # that are added before their drive root are still deduplicated.
    _abs_dirs: list[tuple[str, str]] = []
    for _d in SEARCH_DIRS:
        try:
            _abs = os.path.normcase(os.path.abspath(_d))
        except Exception:
            _abs = _d
        _abs_dirs.append((_d, _abs))

    _deduped: list[str] = []
    for _d, _abs in _abs_dirs:
        if any(
            _o != _abs and (_abs.startswith(_o + os.sep) or _abs == _o)
            for _, _o in _abs_dirs
        ):
            continue  # skip — some other path is an ancestor
        _deduped.append(_d)
    SEARCH_DIRS = _deduped
    # ─────────────────────────────────────────────────────────────────────────

    best_path = None
    best_key = None  # (match_tier, ext_preferred, token_hits); higher tuple wins

    for directory in SEARCH_DIRS:
        if not os.path.exists(directory):
            continue
        # Skip maya project dir (but allow the uploads cache)
        try:
            _dabs = os.path.abspath(directory).lower()
            if _dabs.startswith(maya_dir_lower) and not _dabs.startswith(uploads_dir_lower):
                continue
        except Exception:
            pass
        try:
            for root, dirs, files in os.walk(directory):
                # Skip internal maya dir during walk (but allow the uploads cache)
                try:
                    _rabs = os.path.abspath(root).lower()
                    if _rabs.startswith(maya_dir_lower) and not _rabs.startswith(uploads_dir_lower):
                        dirs.clear()
                        continue
                except Exception:
                    pass
                # Skip heavy/system dirs
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith('.')
                    and d.lower() not in SKIP_DIRS
                ]
                for fname in files:
                    tier, hits = _file_match_tier(fname, query_tokens, query_ext)
                    if tier <= 0:
                        continue
                    full_path = os.path.join(root, fname)
                    full_path, path_error = validate_attachment_path(full_path)
                    if path_error:
                        continue
                    ext = os.path.splitext(fname)[1].lower()
                    ext_pref = 1 if ext in _PREFERRED_EXTS else 0
                    key = (tier, ext_pref, hits)
                    if best_key is None or key > best_key:
                        best_key = key
                        best_path = full_path
                    # Strong, unambiguous hit (all tokens + a real document type):
                    # take it immediately to keep the whole search within seconds.
                    if tier >= 2 and ext_pref == 1:
                        return full_path
        except PermissionError:
            pass
        except Exception:
            pass

    return best_path


def whatsapp_send_file(contact_name: str, file_query: str, caption: str = "", folder_hint: str = "") -> str:
    """
    Sends a file (image, PDF, video, audio, document) to a WhatsApp contact.
    Searches Documents → Downloads → Desktop → all drives for the file.
    Supports contact name OR direct phone number as contact_name.
    Auto-cleans temp copies from uploads cache after sending.
    Args:
        contact_name (str): Name of the contact (e.g. 'Pintu') OR phone number (e.g. '9635385741').
        file_query   (str): Absolute file path OR just a filename/keyword to auto-search (e.g. 'PAY.pdf').
        caption      (str): Optional caption text to send with the file.
        folder_hint  (str): Optional folder name to prioritize (e.g. 'RRB', 'NTPC'). Speeds up search.
    """
    import os
    from backend.tools.desktop.advanced.contacts import lookup_contact
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager, _path_inside, validate_attachment_path
    import re

    if not isinstance(file_query, str) or not file_query.strip():
        return "ERROR: Attachment path is required."
    file_query = file_query.strip()
    if len(file_query) >= 2 and file_query[0] == file_query[-1] and file_query[0] in {"'", '"'}:
        file_query = file_query[1:-1].strip()
    if not file_query:
        return "ERROR: Attachment path is required."

    # 1. Resolve contact — support contact name, raw phone, and WhatsApp synced fallback
    phone = None
    display_name = contact_name
    if re.fullmatch(r'[\d\s\-\+]{7,15}', contact_name.strip()):
        clean_num = re.sub(r'[^\d]', '', contact_name.strip())
        if len(clean_num) == 10:
            phone = "91" + clean_num
        elif len(clean_num) >= 11:
            phone = clean_num
        display_name = contact_name

    if phone is None:
        match = lookup_contact(contact_name)
        if match:
            phone = match["phone"]
            display_name = match["name"]

    if phone is None:
        resolved = whatsapp_manager.resolve_contact(contact_name)
        if resolved.get("success"):
            candidates = resolved.get("candidates", [])
            if len(candidates) > 1:
                return _contact_pick_reply(contact_name, candidates)
            phone = resolved.get("phone")
            display_name = resolved.get("name", contact_name)
        else:
            return _contact_not_found_reply(contact_name, resolved.get("error", ""))

    # Normalize country code
    phone = whatsapp_manager._normalize_phone(phone)
    if not phone:
        return f"ERROR: Invalid phone number for '{display_name}'."

    # 2. Resolve file path. An explicit absolute path is a contract: if it does
    # not exist, fail truthfully instead of fuzzy-searching for a lookalike and
    # silently sending a different file (R05 audit, BUG-020).
    if os.path.isabs(file_query):
        if not os.path.exists(file_query):
            return (f"ERROR: Attachment path '{file_query}' does not exist. "
                    f"No similarly named file was substituted.")
        file_path = file_query
    else:
        file_path = _find_file_in_search_dirs(file_query, folder_hint=folder_hint)
        if not file_path:
            return (f"ERROR: File matching '{file_query}' not found in Documents, Downloads, "
                    f"Desktop, or any drive. Please provide the full file path.")

    file_path, path_error = validate_attachment_path(file_path)
    if path_error:
        return f"ERROR: {path_error}."
    file_name = os.path.basename(file_path)

    # 3. The manager starts and waits for the background service when needed.
    result = whatsapp_manager.send_file(phone, file_path, caption)
    if not result["success"]:
        return f"ERROR: Failed to send '{file_name}' to '{display_name}': {result.get('error')}"

    # 5. Temp cache cleanup — delete if file came from uploads cache
    uploads_dir = os.path.abspath("data/uploads")
    if _path_inside(file_path, uploads_dir):
        try:
            os.remove(file_path)
        except Exception:
            pass

    # 6. Delivery confirmation
    msg_id = result.get("message_id")
    delivery = "pending"
    if msg_id:
        import time
        time.sleep(2)  # Brief wait for WhatsApp to update ack
        delivery = whatsapp_manager.get_message_status(msg_id)

    delivery_icon = {"sent": "Sent", "delivered": "Delivered", "read": "Read",
                     "played": "Played"}.get(delivery, "Pending")
    return (f"SUCCESS: Sent '{file_name}' to '{display_name}' ({phone}). "
            f"Delivery: {delivery_icon}.")


def whatsapp_send_multiple_files(contact_name: str, file_queries: list[str], captions: list[str] = None) -> str:
    """
    Sends multiple files to a WhatsApp contact in one command.
    Searches Documents → Downloads → Desktop → uploads for each file if no absolute path is given.
    Auto-cleans temp copies from uploads cache after each send.
    Args:
        contact_name (str): Name of the contact (e.g. 'Pintu') OR phone number.
        file_queries (list): List of file names or absolute paths (e.g. ['resume.pdf', 'photo.jpg']).
        captions     (list): Optional list of captions for each file (same order as file_queries).
    """
    import os
    from backend.tools.desktop.advanced.contacts import lookup_contact
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager, _path_inside, validate_attachment_path
    import re

    # Resolve contact
    phone = None
    display_name = contact_name
    if re.fullmatch(r'[\d\s\-\+]{7,15}', contact_name.strip()):
        clean_num = re.sub(r'[^\d]', '', contact_name.strip())
        if len(clean_num) == 10:
            phone = "91" + clean_num
        elif len(clean_num) >= 11:
            phone = clean_num
        display_name = contact_name

    if phone is None:
        match = lookup_contact(contact_name)
        if match:
            phone = match["phone"]
            display_name = match["name"]

    if phone is None:
        resolved = whatsapp_manager.resolve_contact(contact_name)
        if resolved.get("success"):
            candidates = resolved.get("candidates", [])
            if len(candidates) > 1:
                return _contact_pick_reply(contact_name, candidates)
            phone = resolved.get("phone")
            display_name = resolved.get("name", contact_name)
        else:
            return _contact_not_found_reply(contact_name, resolved.get("error", ""))

    # Normalize country code
    phone = whatsapp_manager._normalize_phone(phone)
    if not phone:
        return f"ERROR: Invalid phone number for '{display_name}'."

    if not isinstance(file_queries, list) or not 1 <= len(file_queries) <= 10:
        return "ERROR: Provide between 1 and 10 files."

    if captions is None:
        captions = [""] * len(file_queries)
    if len(captions) < len(file_queries):
        captions += [""] * (len(file_queries) - len(captions))

    # Resolve all file paths
    uploads_dir = os.path.abspath("data/uploads")
    files_payload = []
    not_found = []
    duplicate_files = []
    temp_files = []
    seen_paths = set()

    for query, cap in zip(file_queries, captions):
        if not isinstance(query, str) or not query.strip():
            not_found.append("missing attachment path")
            continue
        query = query.strip()
        if len(query) >= 2 and query[0] == query[-1] and query[0] in {"'", '"'}:
            query = query[1:-1].strip()
        if not query:
            not_found.append("missing attachment path")
            continue
        # Same absolute-path contract as whatsapp_send_file (BUG-020): a missing
        # absolute path is an error, never a fuzzy-substituted lookalike file.
        if os.path.isabs(query):
            fp = query if os.path.exists(query) else None
            if not fp:
                not_found.append(f"{query} (path does not exist; no substitute searched)")
                continue
        else:
            fp = _find_file_in_search_dirs(query)
        if not fp:
            not_found.append(query)
        else:
            fp, path_error = validate_attachment_path(fp)
            if path_error:
                not_found.append(f"{query} ({path_error})")
                continue
            if fp in seen_paths:
                duplicate_files.append(os.path.basename(fp))
                continue
            seen_paths.add(fp)
            files_payload.append({"filePath": fp, "caption": cap})
            if _path_inside(fp, uploads_dir):
                temp_files.append(fp)

    if not files_payload:
        detail = "; ".join(not_found) if not_found else ""
        suffix = f" ({detail})" if detail else ""
        return f"ERROR: No safe attachment files were found to send.{suffix}"

    # The manager starts and waits for the background service when needed.
    results = whatsapp_manager.send_files(phone, files_payload)

    # Temp cache cleanup — only for uploads-cache copies whose send actually
    # succeeded. Deleting after a FAILED send would destroy the user's only
    # copy and make a retry impossible (R05 audit, BUG-021).
    delivered_paths = {
        os.path.normcase(os.path.abspath(r.get("file", "")))
        for r in results if r.get("success")
    }
    for tf in temp_files:
        if os.path.normcase(os.path.abspath(tf)) not in delivered_paths:
            continue
        try:
            os.remove(tf)
        except Exception:
            pass

    # Build summary report
    success_count = sum(1 for r in results if r.get("success"))
    if success_count == len(file_queries):
        prefix = "SUCCESS"
    elif success_count:
        prefix = "PARTIAL"
    else:
        prefix = "ERROR"
    lines = [f"{prefix}: File delivery results for '{display_name}' ({phone}):"]
    for r in results:
        fname = os.path.basename(r.get("file", "?"))
        if r.get("success"):
            lines.append(f"  ✅ {fname} — Sent (ID: {r.get('messageId','?')})")
        else:
            lines.append(f"  ❌ {fname} — Failed: {r.get('error','unknown error')}")
    for nf in not_found:
        lines.append(f"  ⚠️ '{nf}' — File not found on PC (searched Documents/Downloads/Desktop/uploads)")
    for duplicate in duplicate_files:
        lines.append(f"  ⚠️ {duplicate} — Duplicate attachment skipped")

    lines.append(f"\n{success_count}/{len(file_queries)} files sent successfully.")
    return "\n".join(lines)


def list_processes(sort_by: str = "cpu") -> str:
    """List top running processes sorted by cpu/mem/name. Returns formatted table."""
    try:
        sort_key = {"cpu": "cpu_percent", "mem": "memory_percent", "name": "name"}
        key = sort_key.get(sort_by, "cpu_percent")
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x.get(key, 0) or 0, reverse=True)
        lines = [f"{'PID':>6} {'CPU%':>5} {'MEM%':>5}  Name"]
        for p in procs[:30]:
            lines.append(f"{p['pid']:>6} {p['cpu_percent'] or 0:>5.1f} {p['memory_percent'] or 0:>5.1f}  {p['name']}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERR: {e}"


def get_battery_info() -> str:
    """Get battery percentage, charging status, time left, power plan."""
    try:
        batt = psutil.sensors_battery()
        if not batt:
            return "No battery detected (desktop or VM)."
        plug = "Charging" if batt.power_plugged else "On battery"
        pct = batt.percent
        secs = batt.secsleft
        time_str = ""
        if secs != psutil.POWER_TIME_UNLIMITED and secs != psutil.POWER_TIME_UNKNOWN:
            h, m = divmod(secs // 60, 60)
            time_str = f" ({h}h {m}m remaining)" if not batt.power_plugged else f" ({h}h {m}m to full)"
        # Power plan from PowerShell
        plan = "n/a"
        try:
            r = subprocess.run(["powershell", "-NoProfile", "(Get-CimInstance -Namespace root\\cimv2\\power -ClassName Win32_PowerPlan -Filter 'IsActive=True').ElementName"],
                               capture_output=True, text=True, timeout=5)
            plan = r.stdout.strip() if r.stdout.strip() else "n/a"
        except Exception:
            pass
        return f"Battery: {pct:.0f}% {plug}{time_str}\nPower plan: {plan}"
    except Exception as e:
        return f"ERR: {e}"


def get_network_info() -> str:
    """Get IP address, active network interfaces, and connection status."""
    try:
        import socket
        host = socket.gethostname()
        local_ip = "n/a"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("1.1.1.1", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        lines = [f"Host: {host}", f"Local IP: {local_ip}"]
        for name in sorted(addrs):
            if name.startswith("Loopback") or name == "lo":
                continue
            s = stats.get(name)
            up = "Up" if s and s.isup else "Down"
            ip_list = ", ".join(a.address for a in addrs[name] if a.family.name == "AF_INET")
            if ip_list:
                lines.append(f"  {name}: {up} — {ip_list}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERR: {e}"
