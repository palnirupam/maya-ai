"""System verifier utilities: SHA256 checksum verification for downloads/binaries."""
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def verify_file_sha256(file_path: str | Path, expected_hash: str) -> bool:
    """
    Computes SHA256 of file_path and compares against expected_hash (case-insensitive).
    Raises ValueError on checksum mismatch or FileNotFoundError if missing.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Binary file for verification does not exist: {path}")

    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    actual_hash = sha256.hexdigest().lower()
    expected = expected_hash.strip().lower()

    if actual_hash != expected:
        msg = (
            f"Checksum verification failed for '{path.name}'! "
            f"Expected SHA256: {expected}, got: {actual_hash}. Download rejected."
        )
        logger.error(f"[SECURITY] {msg}")
        raise ValueError(msg)

    logger.info(f"[SECURITY] Checksum verified successfully for {path.name}.")
    return True
