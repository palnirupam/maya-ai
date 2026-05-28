import os
import subprocess
import hashlib
import base64
import logging
from cryptography.fernet import Fernet
from pathlib import Path

KEY_FILE = Path("data/.fernet_key")
_logger = logging.getLogger(__name__)

def _get_hardware_fingerprint() -> str:
    try:
        if os.name == 'nt':
            # Windows: Get Motherboard Serial and CPU ID using powershell
            cpu_cmd = 'powershell -NoProfile -Command "(Get-CimInstance Win32_Processor).ProcessorId"'
            board_cmd = 'powershell -NoProfile -Command "(Get-CimInstance Win32_BaseBoard).SerialNumber"'
            cpu_id = subprocess.check_output(cpu_cmd, shell=True).decode().strip()
            board_id = subprocess.check_output(board_cmd, shell=True).decode().strip()
            return f"{board_id}_{cpu_id}"
        else:
            # Linux/Mac fallback (for cross-platform testing)
            import uuid
            return str(uuid.getnode())
    except Exception:
        return "fallback_static_fingerprint_for_safety"

def _get_or_create_key() -> bytes:
    """
    Generates a 32-byte Fernet-compatible key using PBKDF2
    based on the hardware fingerprint.
    """
    fingerprint = _get_hardware_fingerprint()
    # Use PBKDF2 to derive a secure 32-byte key
    # Salt is dynamically generated and stored securely
    salt_file = Path("data/.salt")
    if salt_file.exists():
        with open(salt_file, "rb") as f:
            salt = f.read()
    else:
        import os
        salt = os.urandom(16)
        salt_file.parent.mkdir(parents=True, exist_ok=True)
        with open(salt_file, "wb") as f:
            f.write(salt)

    derived_key = hashlib.pbkdf2_hmac(
        'sha256',
        fingerprint.encode('utf-8'),
        salt,
        100000,
        dklen=32
    )
    # Fernet requires url-safe base64 encoded 32-byte key
    return base64.urlsafe_b64encode(derived_key)

FERNET_KEY = _get_or_create_key()
cipher = Fernet(FERNET_KEY)

class CryptoManager:
    @staticmethod
    def encrypt(data: str) -> str:
        if not data:
            return ""
        return cipher.encrypt(data.encode()).decode()
        
    @staticmethod
    def decrypt(token: str) -> str:
        if not token:
            return ""
        try:
            return cipher.decrypt(token.encode()).decode()
        except Exception as e:
            _logger.error(f"[CRYPTO] Decryption failed — possible key mismatch or tampered data: {e}")
            return ""

crypto_manager = CryptoManager()
