import logging

from .crypto import crypto_manager
from .models import UserPreferences

logger = logging.getLogger(__name__)


# Defaults used when a permission preference is absent or cannot be decrypted.
# Keep terminal and auto-approve off by default; dangerous system/file actions
# still go through agent_team's approval gate even when their tool is available.
PERMISSION_DEFAULTS: dict[str, bool] = {
    "PERM_BROWSER": True,
    "PERM_FILESYSTEM": True,
    "PERM_TERMINAL": False,
    "PERM_SYSTEM": True,
    "PERM_AUTO_APPROVE": False,
    "PERM_WEB_SEARCH": True,
}


def decrypt_pref_value(pref) -> str:
    """Return a decrypted UserPreferences value, or an empty string."""
    if not pref or not pref.value:
        return ""
    try:
        return (crypto_manager.decrypt(pref.value) or "").strip()
    except Exception as exc:
        logger.warning(f"Failed to decrypt preference {getattr(pref, 'key', '?')}: {exc}")
        return ""


def read_bool_pref(db, key: str, default: bool = False) -> bool:
    """Read a boolean UserPreferences value.

    Explicit readable values win. Missing or unreadable values use `default` so
    a corrupted local encryption state cannot silently remove core agent tools.
    """
    pref = db.query(UserPreferences).filter(UserPreferences.key == key).first()
    if pref and pref.value:
        value = decrypt_pref_value(pref).lower()
        if value == "true":
            return True
        if value == "false":
            return False
        logger.warning(
            f"Preference {key} is present but unreadable; using default={default}."
        )
    return default


def read_permission_pref(db, key: str) -> bool:
    return read_bool_pref(db, key, PERMISSION_DEFAULTS.get(key, False))
