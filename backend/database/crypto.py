import os
import subprocess
import hashlib
import base64
import logging
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from pathlib import Path

import ctypes

from backend.config.runtime_paths import DATA_DIR


class KeyUnreadableError(Exception):
    """Raised when data cannot be decrypted due to hardware key mismatch or DPAPI failure."""
    pass

recovery_required = False



class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def win_dpapi_encrypt(data: bytes) -> bytes:
    """Encrypt raw bytes using Windows DPAPI (CryptProtectData)."""
    if os.name != "nt" or os.getenv("MAYA_TESTING") == "1":
        return data
    try:
        data_in = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_ubyte)))
        data_out = _DATA_BLOB()
        if ctypes.windll.crypt32.CryptProtectData(ctypes.byref(data_in), "MayaSaltKey", None, None, None, 0, ctypes.byref(data_out)):
            buf = ctypes.string_at(data_out.pbData, data_out.cbData)
            ctypes.windll.kernel32.LocalFree(data_out.pbData)
            return buf
    except Exception as e:
        logging.getLogger(__name__).warning(f"[DPAPI] CryptProtectData error: {e}")
    return data


def win_dpapi_decrypt(data: bytes) -> bytes:
    """Decrypt bytes using Windows DPAPI (CryptUnprotectData)."""
    if os.name != "nt" or os.getenv("MAYA_TESTING") == "1":
        return data
    try:
        data_in = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_ubyte)))
        data_out = _DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)):
            buf = ctypes.string_at(data_out.pbData, data_out.cbData)
            ctypes.windll.kernel32.LocalFree(data_out.pbData)
            return buf
    except Exception as e:
        logging.getLogger(__name__).warning(f"[DPAPI] CryptUnprotectData error: {e}")
    raise KeyUnreadableError("DPAPI decryption failed: unauthorized user account or corrupted salt file.")


KEY_FILE = DATA_DIR / ".fernet_key"      # legacy random-key file (pre hardware-key migration)
SALT_FILE = DATA_DIR / ".salt"
FP_CACHE_FILE = DATA_DIR / ".fp_check"   # sha256 of the primary fingerprint (drift detection only)

_logger = logging.getLogger(__name__)



def _run(cmd: str) -> str:
    """Run a shell command, return first non-empty stripped line, or '' on any failure.

    timeout=5 ensures that a hung WMI/PowerShell probe (common on Windows
    systems with a corrupted WMI repository) never blocks backend startup.
    """
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5)
        for line in out.decode(errors="ignore").splitlines():
            line = line.strip()
            if line:
                return line
    except Exception:
        pass
    return ""


def _hardware_components() -> tuple[str, str]:
    """Return (board_serial, cpu_id). Either may be '' if that probe failed."""
    if os.getenv("MAYA_TESTING") == "1":
        return "maya-test-board", "maya-test-cpu"
    if os.name == "nt":
        cpu_id = _run('powershell -NoProfile -Command "(Get-CimInstance Win32_Processor).ProcessorId"')
        board_id = _run('powershell -NoProfile -Command "(Get-CimInstance Win32_BaseBoard).SerialNumber"')
        return board_id, cpu_id
    else:
        import uuid
        return str(uuid.getnode()), ""


def _get_hardware_fingerprint() -> str:
    """Primary fingerprint used for NEW encryption. Kept in the original
    `{board}_{cpu}` format for backward compatibility, but only when BOTH
    hardware probes succeeded. If either probe is empty we use the stable
    fallback string — that prevents an outage-window from writing data under
    an unstable `{board}_` / `_{cpu}` / `_` key that is NOT recoverable once
    the probes come back.
    """
    board_id, cpu_id = _hardware_components()
    if not board_id or not cpu_id:
        return "fallback_static_fingerprint_for_safety"
    return f"{board_id}_{cpu_id}"


def _candidate_fingerprints() -> list[str]:
    """All fingerprint strings that MIGHT have been used to encrypt existing data.

    Fingerprint drift on Windows is common: a WMI probe can intermittently return
    empty, so `{board}_{cpu}` may have been `{board}_`, `_{cpu}`, the fallback, or a
    node-based value at different times. We derive candidate keys from every such
    variant so previously-stored data stays recoverable instead of being lost.
    Ordered by likelihood; the first is always the current primary fingerprint.
    """
    board_id, cpu_id = _hardware_components()
    seen, candidates = set(), []

    def add(fp: str):
        if fp and fp not in seen:
            seen.add(fp)
            candidates.append(fp)

    add(f"{board_id}_{cpu_id}")          # current primary
    add(f"{board_id}_")                  # cpu probe was empty at encrypt time
    add(f"_{cpu_id}")                    # board probe was empty at encrypt time
    add("_")                             # primary from a transient outage before the fix
    add(board_id)
    add(cpu_id)
    try:
        import uuid
        add(str(uuid.getnode()))         # cross-platform / earlier fallback path
    except Exception:
        pass
    add("fallback_static_fingerprint_for_safety")
    return candidates


def _load_salt() -> bytes:
    global recovery_required
    if SALT_FILE.exists():
        with open(SALT_FILE, "rb") as f:
            raw = f.read()
        try:
            return win_dpapi_decrypt(raw)
        except KeyUnreadableError:
            # Fallback if unencrypted legacy salt exists
            if len(raw) == 16:
                return raw
            recovery_required = True
            return os.urandom(16)
    salt = os.urandom(16)
    SALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    encrypted_salt = win_dpapi_encrypt(salt)
    with open(SALT_FILE, "wb") as f:
        f.write(encrypted_salt)
    _harden(SALT_FILE)
    return salt


def _derive_key(fingerprint: str, salt: bytes) -> bytes:
    derived = hashlib.pbkdf2_hmac("sha256", fingerprint.encode("utf-8"), salt, 100_000, dklen=32)
    return base64.urlsafe_b64encode(derived)


def _harden(path: Path):
    """Best-effort: hide + restrict the secret file to the current user only."""
    if os.getenv("MAYA_TESTING") == "1":
        return
    try:
        if os.name == "nt":
            subprocess.run(f'attrib +h "{path}"', shell=True, capture_output=True)
            # Reset ACL to owner-only (remove inherited access).
            subprocess.run(f'icacls "{path}" /inheritance:r /grant:r "%USERNAME%:F"',
                           shell=True, capture_output=True)
        else:
            os.chmod(path, 0o600)
    except Exception:
        pass


def _build_ciphers() -> tuple[MultiFernet, Fernet]:
    """Build the decryption chain (tries all candidate keys) and the primary
    encryption cipher. The primary is derived from the STABLE current fingerprint
    so new data is never encrypted under a transient '_' key.
    Returns (multi, primary)."""
    salt = _load_salt()

    primary_fp = _get_hardware_fingerprint()
    keys: list[Fernet] = [Fernet(_derive_key(primary_fp, salt))]
    seen = {primary_fp}
    for fp in _candidate_fingerprints():
        if fp not in seen:
            seen.add(fp)
            keys.append(Fernet(_derive_key(fp, salt)))

    # Include a legacy random key file if one still exists (pre-migration installs).
    if KEY_FILE.exists():
        try:
            with open(KEY_FILE, "rb") as f:
                keys.append(Fernet(f.read().strip()))
        except Exception as e:
            _logger.warning(f"[CRYPTO] Legacy key file present but unusable: {e}")

    return MultiFernet(keys), keys[0]


def _fingerprint_drift_check():
    """Loudly warn (do NOT silently switch) if the primary fingerprint changed
    since last run, and warn if we are running on the unstable fallback."""
    fp = _get_hardware_fingerprint()
    digest = hashlib.sha256(fp.encode()).hexdigest()
    if fp == "fallback_static_fingerprint_for_safety":
        _logger.error("[CRYPTO] Hardware fingerprint UNAVAILABLE — using fallback. "
                      "WMI/PowerShell probes failed; encryption key is unstable this run.")
    try:
        if FP_CACHE_FILE.exists():
            prev = FP_CACHE_FILE.read_text().strip()
            if prev and prev != digest:
                _logger.warning("[CRYPTO] Hardware fingerprint CHANGED since last run. "
                                "Existing data will be recovered via candidate keys and "
                                "re-encrypted under the new key.")
        else:
            FP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        FP_CACHE_FILE.write_text(digest)
        _harden(FP_CACHE_FILE)
    except Exception:
        pass


_fingerprint_drift_check()
_multi, _primary = _build_ciphers()

# Backward-compat exports used elsewhere (e.g. reencrypt_wizard).
# Keep this aligned with the current encryption primary so there's no drift.
FERNET_KEY = _derive_key(_get_hardware_fingerprint(), _load_salt())
cipher = _primary


class CryptoManager:
    @staticmethod
    def encrypt(data: str) -> str:
        if not data:
            return ""
        return _primary.encrypt(data.encode()).decode()

    @staticmethod
    def decrypt(token: str, raise_on_failure: bool = False) -> str:
        """Decrypt using any known candidate key. If token is invalid or unreadable,
        raises KeyUnreadableError when raise_on_failure=True, otherwise returns ''."""
        if not token:
            return ""
        try:
            return _multi.decrypt(token.encode()).decode()
        except InvalidToken:
            _logger.error("[CRYPTO] Decryption failed — no candidate key matched "
                          "(data encrypted on different hardware, or tampered).")
            if raise_on_failure:
                raise KeyUnreadableError("Data cannot be decrypted: key mismatch or tampered data.")
            return ""
        except Exception as e:
            _logger.error(f"[CRYPTO] Decryption error: {e}")
            if raise_on_failure:
                raise KeyUnreadableError(f"Decryption error: {e}")
            return ""

    @staticmethod
    def needs_rotation(token: str) -> bool:

        """True if the token decrypts with a non-primary candidate key and should
        be re-encrypted under the primary key."""
        if not token:
            return False
        try:
            _primary.decrypt(token.encode())
            return False
        except InvalidToken:
            return CryptoManager.decrypt(token) != "" or _decryptable(token)
        except Exception:
            return False

    @staticmethod
    def rotate(token: str) -> str:
        """Re-encrypt a token under the primary key if it was stored under an old
        candidate key. Returns the (possibly unchanged) token."""
        if not token:
            return token
        try:
            return _multi.rotate(token.encode()).decode()
        except Exception:
            return token


def _decryptable(token: str) -> bool:
    try:
        _multi.decrypt(token.encode())
        return True
    except Exception:
        return False


crypto_manager = CryptoManager()
