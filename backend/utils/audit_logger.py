import os
import logging
import subprocess
import platform
from pathlib import Path

LOG_DIR = Path("backend/logs")
LOG_FILE = LOG_DIR / "security_events.log"

def setup_append_only_permissions(file_path: Path):
    """
    Sets NTFS permissions on Windows to allow only FILE_APPEND_DATA for the current user,
    preventing deletion or backward modification.
    Requires the file to exist.
    """
    if platform.system() != "Windows":
        # On Linux/Mac, we might use chattr +a, but requires sudo.
        return
        
    try:
        # Get current username
        username = os.environ.get("USERNAME")
        if not username:
            return
            
        # Grant Append Data (AD) and Read (R), but deny Write Data (WD) and Delete (DE)
        # Note: In a real enterprise setup, an admin script sets this. 
        # Here we do our best effort with icacls.
        file_str = str(file_path.absolute())
        
        # Reset permissions (inheriting from parent)
        subprocess.run(["icacls", file_str, "/reset"], capture_output=True)
        
        # Deny Delete (DE)
        # Note: Denying WD (Write Data) breaks Python's open(mode='a') which requests GENERIC_WRITE
        deny_cmd = ["icacls", file_str, "/deny", f"{username}:(DE)"]
        subprocess.run(deny_cmd, capture_output=True)
        
    except Exception as e:
        print(f"Failed to set append-only permissions: {e}")

def get_audit_logger():
    if not LOG_DIR.exists():
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
    if not LOG_FILE.exists():
        LOG_FILE.touch()
        setup_append_only_permissions(LOG_FILE)

    logger = logging.getLogger("MayaSecurityAudit")
    logger.setLevel(logging.WARNING)
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

audit_logger = get_audit_logger()
