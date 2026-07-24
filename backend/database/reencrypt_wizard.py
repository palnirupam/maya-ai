"""
Hardware migration recovery wizard for Maya AI database encryption.

When a hardware migration occurs (e.g. motherboard/CPU change, or DB moved to new PC),
this module detects unreadable records, provides database backup, and re-encrypts
user preferences and memories with the current machine's primary Fernet key.
"""
import logging
import shutil
from pathlib import Path
from typing import List, Tuple

from backend.database.connection import SessionLocal
from backend.database.crypto import CryptoManager, crypto_manager, KeyUnreadableError
from backend.database.models import UserPreferences, LongTermMemory

logger = logging.getLogger(__name__)


def backup_database(db_path: Path, backup_path: Path) -> bool:
    """Creates a timestamped/safe copy of the database before running recovery."""
    try:
        if db_path.exists():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, backup_path)
            logger.info(f"[REENCRYPT] Database backed up to {backup_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"[REENCRYPT] Database backup failed: {e}")
        return False


def check_database_keys_readable(db=None) -> Tuple[bool, List[str]]:
    """
    Scans encrypted user preferences and returns:
      (is_all_readable, list_of_unreadable_preference_keys)
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    unreadable_keys = []
    try:
        prefs = db.query(UserPreferences).all()
        for p in prefs:
            if p.value:
                try:
                    decrypted = crypto_manager.decrypt(p.value, raise_on_failure=True)
                    if not decrypted and p.value:
                        unreadable_keys.append(p.key)
                except KeyUnreadableError:
                    unreadable_keys.append(p.key)
                except Exception:
                    unreadable_keys.append(p.key)
        return (len(unreadable_keys) == 0, unreadable_keys)
    except Exception as e:
        logger.error(f"[REENCRYPT] Failed to check database key readability: {e}")
        return (False, ["<database_error>"])
    finally:
        if close_db:
            db.close()


def reencrypt_preference(key: str, plaintext_value: str, db=None) -> bool:
    """
    Re-encrypts a preference with the current primary hardware key and saves to DB.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        encrypted_val = crypto_manager.encrypt(plaintext_value)
        pref = db.query(UserPreferences).filter(UserPreferences.key == key).first()
        if pref:
            pref.value = encrypted_val
        else:
            pref = UserPreferences(key=key, value=encrypted_val)
            db.add(pref)
        db.commit()
        logger.info(f"[REENCRYPT] Re-encrypted preference key '{key}' successfully.")
        return True
    except Exception as e:
        logger.error(f"[REENCRYPT] Re-encryption failed for key '{key}': {e}")
        if db:
            db.rollback()
        return False
    finally:
        if close_db:
            db.close()
