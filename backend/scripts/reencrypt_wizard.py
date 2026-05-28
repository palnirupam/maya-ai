"""
Re-encryption Wizard - Step 2
Decrypts DB with old Fernet key and re-encrypts with new Hardware key.
"""
import sys
import os

# Run from c:\maya-ai root
sys.path.insert(0, os.path.abspath("."))

from pathlib import Path
from cryptography.fernet import Fernet
import shutil

OLD_KEY_FILE = Path("data/.fernet_key")
DB_PATH = Path("data/memory.db")
BACKUP_PATH = Path("data/memory.db.backup")

def main():
    print("=" * 60)
    print("Maya AI - Re-encryption Wizard")
    print("=" * 60)

    # Step 1: Check old key exists
    if not OLD_KEY_FILE.exists():
        print(f"\n[INFO] Old key file ({OLD_KEY_FILE}) not found.")
        print("[INFO] This means DB data is already using the new hardware key, or no key existed before.")
        print("[OK] No migration needed.")
        return

    # Step 2: Load old Fernet key
    with open(OLD_KEY_FILE, "rb") as f:
        old_key = f.read().strip()
    old_cipher = Fernet(old_key)
    print(f"\n[OK] Old Fernet key loaded: {OLD_KEY_FILE}")

    # Step 3: Load new hardware-based key
    from backend.database.crypto import crypto_manager, FERNET_KEY
    print(f"[OK] New Hardware Fingerprint key loaded.")

    # Step 4: Backup DB
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"[OK] Database backup complete: {BACKUP_PATH}")
    else:
        print(f"[WARN] Database ({DB_PATH}) not found.")

    # Step 5: Read and migrate all encrypted values in UserPreferences
    from backend.database.connection import SessionLocal
    from backend.database.models import UserPreferences

    db = SessionLocal()
    migrated = 0
    skipped = 0
    try:
        prefs = db.query(UserPreferences).all()
        for pref in prefs:
            if isinstance(pref.value, str) and len(pref.value) > 20:
                try:
                    # Try decrypting with old key
                    old_decrypted = old_cipher.decrypt(pref.value.encode()).decode()
                    # Re-encrypt with new key
                    new_encrypted = crypto_manager.encrypt(old_decrypted)
                    pref.value = new_encrypted
                    migrated += 1
                    print(f"  [MIGRATED] {pref.key}")
                except Exception:
                    # Already in new format or plain value - skip
                    skipped += 1
                    print(f"  [SKIP] {pref.key}")

        db.commit()
        print(f"\n[DONE] {migrated} values migrated, {skipped} skipped.")

    finally:
        db.close()

    # Step 6: Delete old key file
    OLD_KEY_FILE.unlink()
    print(f"[OK] Old key file deleted: {OLD_KEY_FILE}")
    print("\n[SUCCESS] Re-encryption complete! Maya can now be started.")
    print("=" * 60)

if __name__ == "__main__":
    main()
