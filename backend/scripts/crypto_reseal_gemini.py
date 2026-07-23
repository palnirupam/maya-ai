"""
Re-seal Gemini credentials
==========================
The 3 GEMINI_* preference rows were encrypted under an old key and can no
longer be decrypted (the other 17 rows are fine — the current hardware key
works). This script:

  1. Backs up data/memory.db.
  2. Re-encrypts GEMINI_API_KEY (taken from .env, or an explicit --key) under
     the CURRENT working key so it decrypts cleanly and stops the log spam.
  3. Deletes the stale GEMINI_API_PROVIDER / GEMINI_ACTIVE_MODEL rows so the
     adapter's provider auto-detection runs fresh.

Run from c:\\maya-ai root:
    python backend/scripts/crypto_reseal_gemini.py            # dry run
    python backend/scripts/crypto_reseal_gemini.py --apply    # write changes
    python backend/scripts/crypto_reseal_gemini.py --apply --key <API_KEY>
"""
import sys, os, shutil, sqlite3, argparse
sys.path.insert(0, os.path.abspath("."))

DB = "data/memory.db"


def _stamp():
    con = sqlite3.connect(":memory:")
    v = con.execute("SELECT strftime('%Y%m%d-%H%M%S','now')").fetchone()[0]
    con.close()
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--key", default=None, help="Gemini API key (defaults to .env GEMINI_API_KEY)")
    args = ap.parse_args()

    # Load .env so we can read the key the same way the app does.
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(".env").resolve(), override=False)
    except Exception:
        pass

    key = (args.key or os.getenv("GEMINI_API_KEY") or "").strip()

    from backend.database.crypto import crypto_manager

    print("=" * 60)
    print("RE-SEAL GEMINI", "(APPLY)" if args.apply else "(DRY RUN)")
    print("=" * 60)

    if not key:
        print("[ERROR] No key found in --key or .env GEMINI_API_KEY. Nothing to seal.")
        print("        Put your key in .env first, then re-run.")
        return

    print(f"Key source : {'--key arg' if args.key else '.env'}  (prefix {key[:4]}..., len {len(key)})")

    if args.apply:
        dst = f"{DB}.bak-{_stamp()}"
        shutil.copy2(DB, dst)
        print(f"[OK] Backup: {dst}")

    # IMPORTANT: user_preferences.value is a SQLAlchemy JSON column. The app
    # reads it with json.loads(), so the stored text must be a JSON string
    # (i.e. json.dumps(token) -> the token wrapped in quotes), NOT the bare
    # Fernet token. We therefore store json.dumps(enc). (Reading via the ORM
    # first is impossible here because the currently-broken row can't be
    # json-decoded, so we use raw sqlite3.)
    import json

    enc = crypto_manager.encrypt(key)
    # sanity: confirm it round-trips with the CURRENT key before writing.
    assert crypto_manager.decrypt(enc) == key, "re-encryption did not round-trip!"
    stored = json.dumps(enc)  # what SQLAlchemy's JSON column would persist

    print("[PLAN] GEMINI_API_KEY -> re-seal under current key (round-trip verified, JSON-encoded)")
    for k in ("GEMINI_API_PROVIDER", "GEMINI_ACTIVE_MODEL"):
        print(f"[PLAN] {k} -> delete stale row (auto-detect will rebuild)")

    if args.apply:
        con = sqlite3.connect(DB)
        cur = con.cursor()
        row = cur.execute("SELECT id FROM user_preferences WHERE key='GEMINI_API_KEY'").fetchone()
        if row:
            cur.execute("UPDATE user_preferences SET value=? WHERE key='GEMINI_API_KEY'", (stored,))
        else:
            cur.execute("INSERT INTO user_preferences (key, value) VALUES ('GEMINI_API_KEY', ?)", (stored,))
        cur.execute("DELETE FROM user_preferences WHERE key IN ('GEMINI_API_PROVIDER','GEMINI_ACTIVE_MODEL')")
        con.commit()
        con.close()
        print("\n[DONE] Gemini credentials re-sealed (JSON-encoded). Restart Maya — the "
              "[CRYPTO] Decryption failed spam should be gone.")
    else:
        print("\nDry run only. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
