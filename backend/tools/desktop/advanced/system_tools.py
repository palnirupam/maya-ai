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
    try:
        if action != 'kill':
            return "ERROR: Unsupported action. Only 'kill' is supported."
            
        killed = []
        if pid:
            p = psutil.Process(pid)
            p.kill()
            killed.append(p.name())
        elif process_name:
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                    proc.kill()
                    killed.append(proc.info['name'])
                    
        if killed:
            return f"SUCCESS: Killed processes: {', '.join(killed)}"
        return "No matching processes found to kill."
    except Exception as e:
        return f"ERROR managing processes: {e}"

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

def _open_and_focus_whatsapp() -> tuple:
    """Helper: Open WhatsApp and return the window object, or raise."""
    import pygetwindow as gw
    import time
    
    # Try finding existing window first
    for title_kw in ["WhatsApp", "whatsapp"]:
        windows = gw.getWindowsWithTitle(title_kw)
        if windows:
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.6)
            return win
    
    # Launch WhatsApp
    import os
    try:
        os.startfile("whatsapp://")
    except Exception:
        import subprocess
        subprocess.Popen(["explorer", "whatsapp://"], shell=True)
    
    # Wait up to 6s for it to open
    for _ in range(12):
        time.sleep(0.5)
        windows = gw.getWindowsWithTitle("WhatsApp")
        if windows:
            win = windows[0]
            win.activate()
            time.sleep(0.5)
            return win
    
    raise RuntimeError("Could not open WhatsApp window after 6 seconds.")


def _whatsapp_navigate_to_contact(contact_name: str):
    """Helper: Use Ctrl+F to search and open a WhatsApp chat."""
    import pyautogui
    import time
    
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("backspace")
    pyautogui.write(contact_name, interval=0.05)
    time.sleep(1.5)  # Wait for search results to populate
    pyautogui.press("down")
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(1.0)


def whatsapp_call(contact_name: str) -> str:
    """
    Initiates a WhatsApp call. Note: calling is disabled/unsupported in the Baileys background service.
    Args:
        contact_name (str): The name of the contact to call.
    """
    return f"ERROR: WhatsApp voice or video calling is not supported via the background service. Please send a text message instead to '{contact_name}'."

def whatsapp_send_message(contact_name: str, message: str) -> str:
    """
    Sends a WhatsApp message to a contact in the SQLite contacts database via Baileys background service.
    Args:
        contact_name (str): The name of the contact (e.g. 'Pintu').
        message (str): The text message to send.
    """
    from backend.tools.desktop.advanced.contacts import lookup_contact
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
    
    match = lookup_contact(contact_name)
    if not match:
        return f"ERROR: Contact '{contact_name}' not found in database. Please save it first by saying: save {contact_name} number [phone_number]."
        
    phone = match["phone"]
    
    # Check status
    status = whatsapp_manager.get_status()
    if status.get("status") not in ["connected", "authenticated"]:
        if status.get("hasQr"):
            return f"ERROR: WhatsApp is not connected. A pairing QR code has been generated. Please scan the QR code to connect. If you are on Telegram, send /whatsapp_qr to view and scan the QR code."
        return "ERROR: WhatsApp is not connected. Please pair your account first by scanning the QR code."
        
    success = whatsapp_manager.send_message(phone, message)
    if success:
        return f"SUCCESS: Sent WhatsApp message to '{match['name']}' ({phone}): {message}"
    return f"ERROR: Failed to send WhatsApp message to '{match['name']}' ({phone}) via background service."

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
        download_url (str): The direct URL to download the installer from.
        install_args (str, optional): Arguments for silent installation (e.g. '/quiet /norestart').
    """
    import urllib.request
    import tempfile
    import os
    import subprocess
    
    try:
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, tool_name)
        
        # Download
        urllib.request.urlretrieve(download_url, file_path)
        
        # Install
        if file_path.endswith('.msi'):
            args = install_args or '/quiet /norestart'
            cmd = f'msiexec /i "{file_path}" {args}'
        elif file_path.endswith('.exe'):
            args = install_args or '/silent /verysilent /norestart /sp-'
            cmd = f'"{file_path}" {args}'
        else:
            return f"SUCCESS: Downloaded file to {file_path}. Manual installation required for this file type."
            
        subprocess.run(cmd, shell=True, check=True)
        return f"SUCCESS: Downloaded and silently installed {tool_name}."
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
    home = os.path.expanduser("~")

    # Heavy skip list — directories to never recurse into
    SKIP_DIRS = {
        'node_modules', '.git', '.venv', '__pycache__', '.cache',
        'windows', 'program files', 'program files (x86)', 'programdata',
        '$recycle.bin', 'system volume information', 'recovery',
        'appdata', '.gemini',
    }
    # Also skip the maya project directory
    maya_dir_lower = _MAYA_PROJECT_DIR.lower()

    query_lower = query.lower().strip()
    folder_hint_lower = folder_hint.lower().strip() if folder_hint else ""
    query_ext = os.path.splitext(query_lower)[1] if '.' in query_lower else ''

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

    preferred_result = None
    fallback_result = None

    for directory in SEARCH_DIRS:
        if not os.path.exists(directory):
            continue
        # Skip maya project dir
        try:
            if os.path.abspath(directory).lower().startswith(maya_dir_lower):
                continue
        except Exception:
            pass
        try:
            for root, dirs, files in os.walk(directory):
                # Skip internal maya dir during walk
                try:
                    if os.path.abspath(root).lower().startswith(maya_dir_lower):
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
                    if query_lower in fname.lower():
                        full_path = os.path.join(root, fname)
                        ext = os.path.splitext(fname)[1].lower()
                        # If user specified an extension, match it exactly
                        if query_ext and ext != query_ext:
                            continue
                        if ext in _PREFERRED_EXTS:
                            if preferred_result is None:
                                preferred_result = full_path
                        else:
                            if fallback_result is None:
                                fallback_result = full_path
                        # If we already have a preferred result, return it
                        if preferred_result:
                            return preferred_result
        except PermissionError:
            pass
        except Exception:
            pass

    return preferred_result or fallback_result


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
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
    import re

    # 1. Resolve contact — support both contact name AND raw phone number
    phone = None
    display_name = contact_name
    # Check if contact_name looks like a phone number (digits only, 10-15 chars)
    if re.fullmatch(r'[\d\s\-\+]{7,15}', contact_name.strip()):
        clean_num = re.sub(r'[^\d]', '', contact_name.strip())
        if len(clean_num) == 10:
            phone = "91" + clean_num  # Add India country code
        elif len(clean_num) >= 11:
            phone = clean_num
        display_name = contact_name
    
    if phone is None:
        match = lookup_contact(contact_name)
        if not match:
            return (f"ERROR: Contact '{contact_name}' not found in database. "
                    f"Please save it first: save {contact_name} number [phone_number].")
        phone = match["phone"]
        display_name = match["name"]
        # Ensure phone has country code
        clean_phone = re.sub(r'[^\d]', '', phone)
        if len(clean_phone) == 10:
            phone = "91" + clean_phone
        else:
            phone = clean_phone

    # 2. Resolve file path
    if os.path.isabs(file_query) and os.path.exists(file_query):
        file_path = file_query
    else:
        file_path = _find_file_in_search_dirs(file_query, folder_hint=folder_hint)
        if not file_path:
            return (f"ERROR: File matching '{file_query}' not found in Documents, Downloads, "
                    f"Desktop, or any drive. Please provide the full file path.")

    file_name = os.path.basename(file_path)

    # 3. Check WhatsApp connection
    status = whatsapp_manager.get_status()
    if status.get("status") not in ["connected", "authenticated"]:
        return "ERROR: WhatsApp is not connected. Please pair your account first."

    # 4. Send file
    result = whatsapp_manager.send_file(phone, file_path, caption)
    if not result["success"]:
        return f"ERROR: Failed to send '{file_name}' to '{display_name}': {result.get('error')}"

    # 5. Temp cache cleanup — delete if file came from uploads cache
    uploads_dir = os.path.abspath("data/uploads")
    if file_path.startswith(uploads_dir):
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
        contact_name (str): Name of the contact (e.g. 'Pintu').
        file_queries (list): List of file names or absolute paths (e.g. ['resume.pdf', 'photo.jpg']).
        captions     (list): Optional list of captions for each file (same order as file_queries).
    """
    import os
    from backend.tools.desktop.advanced.contacts import lookup_contact
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager

    # 1. Resolve contact
    match = lookup_contact(contact_name)
    if not match:
        return (f"ERROR: Contact '{contact_name}' not found in database. "
                f"Please save it first: save {contact_name} number [phone_number].")
    phone = match["phone"]

    if captions is None:
        captions = [""] * len(file_queries)
    if len(captions) < len(file_queries):
        captions += [""] * (len(file_queries) - len(captions))

    # 2. Check WhatsApp connection
    status = whatsapp_manager.get_status()
    if status.get("status") not in ["connected", "authenticated"]:
        return "ERROR: WhatsApp is not connected. Please pair your account first."

    # 3. Resolve all file paths
    uploads_dir = os.path.abspath("data/uploads")
    files_payload = []
    not_found = []
    temp_files = []

    for query, cap in zip(file_queries, captions):
        if os.path.isabs(query) and os.path.exists(query):
            fp = query
        else:
            fp = _find_file_in_search_dirs(query)
        if not fp:
            not_found.append(query)
        else:
            files_payload.append({"filePath": fp, "caption": cap})
            if fp.startswith(uploads_dir):
                temp_files.append(fp)

    # 4. Send all files
    results = whatsapp_manager.send_files(phone, files_payload)

    # 5. Temp cache cleanup
    for tf in temp_files:
        try:
            os.remove(tf)
        except Exception:
            pass

    # 6. Build summary report
    lines = [f"📦 Sent files to '{match['name']}' ({phone}):"]
    for r in results:
        fname = os.path.basename(r.get("file", "?"))
        if r.get("success"):
            lines.append(f"  ✅ {fname} — Sent (ID: {r.get('messageId','?')})")
        else:
            lines.append(f"  ❌ {fname} — Failed: {r.get('error','unknown error')}")
    for nf in not_found:
        lines.append(f"  ⚠️ '{nf}' — File not found on PC (searched Documents/Downloads/Desktop/uploads)")

    success_count = sum(1 for r in results if r.get("success"))
    lines.append(f"\n{success_count}/{len(file_queries)} files sent successfully.")
    return "\n".join(lines)
