"""Single source of truth for path safety + permission checks."""
import os
import re


def _canonical(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


_MAYA_DIR = _canonical(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_TEST_RUNTIME_DIR = _canonical(os.path.join(_MAYA_DIR, ".test-runtime"))
_SAFE_KEEP = {
    _canonical(path)
    for path in (
        r"C:\Windows",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\ProgramData",
        r"C:\Recovery",
    )
}

_SENSITIVE_DIRECTORIES = {
    ".aws",
    ".azure",
    ".docker",
    ".gnupg",
    ".kube",
    ".ssh",
}
_SENSITIVE_FILES = {
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "_netrc",
    "application_default_credentials.json",
    "credentials",
    "credentials.json",
    "secrets.json",
    "service-account.json",
    "token.json",
}
_PRIVATE_KEY_NAMES = {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"}
_PRIVATE_KEY_EXTENSIONS = {".key", ".p12", ".pfx", ".pem"}
_SAFE_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}


def is_sensitive_path(path: str) -> bool:
    """Identify paths that may disclose credentials or private key material."""
    try:
        absolute = os.path.abspath(os.fspath(path))
    except (OSError, TypeError, ValueError):
        return True
    parts = [part.lower() for part in re.split(r"[\\/]+", absolute) if part]
    if not parts:
        return False
    if any(part in _SENSITIVE_DIRECTORIES for part in parts[:-1]):
        return True
    name = parts[-1]
    if name in _SENSITIVE_FILES or name in _PRIVATE_KEY_NAMES:
        return True
    if name.startswith(".env") and name not in _SAFE_ENV_TEMPLATES:
        return True
    return os.path.splitext(name)[1] in _PRIVATE_KEY_EXTENSIONS


def is_safe_path(path: str) -> bool:
    if is_sensitive_path(path):
        return False
    try:
        abspath = _canonical(path)
    except (OSError, TypeError, ValueError):
        return False
    if os.getenv("MAYA_TESTING") == "1" and (
        abspath == _TEST_RUNTIME_DIR or abspath.startswith(_TEST_RUNTIME_DIR + os.sep)
    ):
        return True
    # Use a trailing separator so "C:\Windows" does not block "C:\Windows-Backup".
    if any(abspath == r or abspath.startswith(r + os.sep) for r in _SAFE_KEEP):
        return False
    if abspath == _MAYA_DIR or abspath.startswith(_MAYA_DIR + os.sep):
        return False
    return True


def assert_safe_path(path: str) -> None:
    if not is_safe_path(path):
        raise PermissionError(f"Protected path: {path}")
