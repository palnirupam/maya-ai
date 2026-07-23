import hashlib
import os
import secrets
from pathlib import Path

from backend.config.runtime_paths import DATA_DIR

# A small subset of BIP39 wordlist for demonstration
WORDLIST = [
    "abandon", "ability", "able", "about", "above", "absent", "absorb", "abstract",
    "absurd", "abuse", "access", "accident", "account", "accuse", "achieve", "acid",
    "acoustic", "acquire", "across", "act", "action", "actor", "actress", "actual",
    "adapt", "add", "addict", "address", "adjust", "admit", "adult", "advance",
    "advice", "aerobic", "affair", "afford", "afraid", "again", "age", "agent",
    "agree", "ahead", "aim", "air", "airport", "aisle", "alarm", "album", "alcohol",
    "alert", "alien", "all", "alley", "allow", "almost", "alone", "alpha", "already",
    "also", "alter", "always", "amateur", "amazing", "among", "amount", "amused"
] # 64 words for 6 bits each

_RECOVERY_SALT_FILE = DATA_DIR / ".recovery_salt"


def _load_recovery_salt() -> bytes:
    """Load or create a random 32-byte salt for recovery key derivation.

    Security: a static hardcoded salt allows precomputed dictionary/rainbow
    table attacks against stolen backups. A random persisted salt means an
    attacker must also have the salt file to mount an offline attack.
    """
    if _RECOVERY_SALT_FILE.exists():
        return _RECOVERY_SALT_FILE.read_bytes()
    # First-time setup: generate and persist a cryptographically random salt
    salt = os.urandom(32)
    _RECOVERY_SALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _RECOVERY_SALT_FILE.write_bytes(salt)
    # Restrict to owner-only (mirrors crypto.py _harden pattern)
    if os.getenv("MAYA_TESTING") == "1":
        return salt
    try:
        if os.name == "nt":
            import subprocess
            subprocess.run(
                f'icacls "{_RECOVERY_SALT_FILE}" /inheritance:r /grant:r "%USERNAME%:F"',
                shell=True, capture_output=True
            )
        else:
            os.chmod(_RECOVERY_SALT_FILE, 0o600)
    except Exception:
        pass
    return salt


class RecoveryManager:
    @staticmethod
    def generate_seed_phrase() -> str:
        """Generates a 12-word seed phrase."""
        # For a real implementation, 'mnemonic' package is recommended.
        # This is a functional local implementation mapping 72 bits to 12 words (6 bits each).
        random_bytes = secrets.token_bytes(9) # 72 bits
        bits = bin(int.from_bytes(random_bytes, byteorder='big'))[2:].zfill(72)

        words = []
        for i in range(0, 72, 6):
            chunk = bits[i:i+6]
            index = int(chunk, 2)
            words.append(WORDLIST[index])

        return " ".join(words)

    @staticmethod
    def seed_to_key(seed_phrase: str) -> bytes:
        """Derives a backup encryption key from the seed phrase.

        Uses a randomly-generated salt persisted in data/.recovery_salt.
        The salt file must be backed up alongside the encrypted database —
        without it, recovery keys cannot be derived.
        """
        salt = _load_recovery_salt()
        return hashlib.pbkdf2_hmac(
            'sha256',
            seed_phrase.encode('utf-8'),
            salt,
            100_000,
            dklen=32
        )

recovery_manager = RecoveryManager()
