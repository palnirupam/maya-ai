"""
Crypto Doctor - diagnose which encrypted preferences/memories can still be
decrypted with the CURRENT hardware key, and report what is lost.

Read-only. Makes NO changes. Run from c:\\maya-ai root:
    python backend/scripts/crypto_doctor.py
"""
import sys, os, sqlite3, json
sys.path.insert(0, os.path.abspath("."))

DB = "data/memory.db"


def _unwrap_pref(v):
    """user_preferences.value is a SQLAlchemy JSON column (json.dumps-wrapped).
    Read via raw sqlite it keeps its quotes, so decrypting it raw ALWAYS fails
    and healthy prefs get mislabelled 'LOST'. Unwrap to the bare token first."""
    if isinstance(v, str):
        try:
            loaded = json.loads(v)
            if isinstance(loaded, str):
                return loaded
        except Exception:
            pass
    return v

def main():
    from backend.database.crypto import crypto_manager, _get_hardware_fingerprint

    fp = _get_hardware_fingerprint()
    print("=" * 64)
    print("CRYPTO DOCTOR (read-only)")
    print("=" * 64)
    print(f"Current hardware fingerprint : {fp!r}")
    if fp == "fallback_static_fingerprint_for_safety":
        print("  !! WARNING: fingerprint is the FALLBACK value.")
        print("     PowerShell/WMI probably failed -> key is unstable.")
    salt_ok = os.path.exists("data/.salt")
    print(f"data/.salt present           : {salt_ok}")
    print(f"data/.fernet_key present     : {os.path.exists('data/.fernet_key')}")
    print()

    con = sqlite3.connect(DB); cur = con.cursor()

    # --- preferences ---
    print("--- user_preferences ---")
    ok_keys, bad_keys = [], []
    try:
        cur.execute("SELECT key, value FROM user_preferences")
        for k, v in cur.fetchall():
            if not v:
                print(f"  {k:32} EMPTY"); continue
            dec = crypto_manager.decrypt(_unwrap_pref(v))
            if dec:
                ok_keys.append(k)
                print(f"  {k:32} OK")
            else:
                bad_keys.append(k)
                print(f"  {k:32} *** DECRYPT FAILED (lost) ***")
    except Exception as e:
        print("  (no user_preferences table or error:", e, ")")

    # --- long term memories ---
    print("\n--- long_term_memory (sample) ---")
    mem_ok = mem_bad = 0
    for tbl in ("long_term_memory", "memories", "memory"):
        try:
            cur.execute(f"SELECT category, content FROM {tbl} LIMIT 200")
            rows = cur.fetchall()
        except Exception:
            continue
        for cat, content in rows:
            if crypto_manager.decrypt(content) or crypto_manager.decrypt(cat):
                mem_ok += 1
            else:
                mem_bad += 1
        print(f"  table {tbl}: {mem_ok} decryptable, {mem_bad} lost")
        break
    else:
        print("  (no memory table found)")

    con.close()

    print("\n" + "=" * 64)
    print(f"SUMMARY: {len(ok_keys)} prefs OK, {len(bad_keys)} prefs LOST")
    if bad_keys:
        print("Lost / need re-entry:")
        for k in bad_keys:
            print(f"   - {k}")
    print("=" * 64)

if __name__ == "__main__":
    main()
