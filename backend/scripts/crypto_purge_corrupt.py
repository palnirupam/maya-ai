"""
Purge Corrupt Encrypted Rows
============================
Removes user_preferences rows whose encrypted value can NO LONGER be decrypted
by any candidate key (e.g. keys encrypted under a since-changed salt/hardware).
These rows are permanently unreadable and only cause repeated
"[CRYPTO] Decryption failed" spam at runtime.

After purging, re-enter the keys via Settings (or the .env file), which will
store them freshly under the current primary key.

Safe by design:
  * Backs up data/memory.db first.
  * Only deletes rows that fail decryption under EVERY candidate key.
  * Long-term memories / scheduled tasks are reported but NOT deleted
    (they are data, not credentials) unless --include-memory is passed.

Usage (from c:\\maya-ai root):
    python backend/scripts/crypto_purge_corrupt.py            # dry run
    python backend/scripts/crypto_purge_corrupt.py --apply    # delete corrupt prefs
"""
import sys, os, shutil, sqlite3, argparse, json
sys.path.insert(0, os.path.abspath("."))

DB = "data/memory.db"


def _unwrap_pref(v):
    """user_preferences.value is a SQLAlchemy JSON column, so the stored token is
    json.dumps-wrapped (e.g. '"gAAAA..."'). Read via raw sqlite it keeps those
    quotes, so a Fernet decrypt of it ALWAYS fails — which previously flagged
    EVERY healthy credential as 'corrupt' and, with --apply, DELETED it. Unwrap
    to the bare token first. Non-preference tables store bare tokens already."""
    if isinstance(v, str):
        try:
            loaded = json.loads(v)
            if isinstance(loaded, str):
                return loaded
        except Exception:
            pass
    return v


def _stamp():
    con = sqlite3.connect(":memory:")
    v = con.execute("SELECT strftime('%Y%m%d-%H%M%S','now')").fetchone()[0]
    con.close()
    return v


def _recoverable(multi, token: str) -> bool:
    try:
        multi.decrypt(token.encode())
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-memory", action="store_true",
                    help="also purge unreadable long_term_memory rows")
    args = ap.parse_args()

    from backend.database.crypto import _multi

    print("=" * 64)
    print("PURGE CORRUPT ROWS", "(APPLY)" if args.apply else "(DRY RUN)")
    print("=" * 64)

    if args.apply:
        dst = f"{DB}.bak-{_stamp()}"
        shutil.copy2(DB, dst)
        print(f"[OK] Backup: {dst}\n")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # preferences (credentials) -----------------------------------------
    corrupt_prefs = []
    for row in cur.execute("SELECT id, key, value FROM user_preferences").fetchall():
        v = _unwrap_pref(row["value"])
        if v and isinstance(v, str) and len(v) >= 20 and not _recoverable(_multi, v):
            corrupt_prefs.append((row["id"], row["key"]))

    print(f"user_preferences: {len(corrupt_prefs)} corrupt / unreadable")
    for _id, key in corrupt_prefs:
        print(f"   [PURGE] {key}")
        if args.apply:
            cur.execute("DELETE FROM user_preferences WHERE id=?", (_id,))

    # long-term memory (optional) ---------------------------------------
    try:
        mem_rows = cur.execute("SELECT id, content FROM long_term_memory").fetchall()
        corrupt_mem = [r["id"] for r in mem_rows
                       if r["content"] and not _recoverable(_multi, r["content"])]
        print(f"\nlong_term_memory: {len(corrupt_mem)} unreadable "
              f"({'will purge' if args.include_memory else 'kept — pass --include-memory to remove'})")
        if args.apply and args.include_memory:
            for _id in corrupt_mem:
                cur.execute("DELETE FROM long_term_memory WHERE id=?", (_id,))
    except Exception:
        pass

    if args.apply:
        con.commit()
        print("\n[DONE] Corrupt rows removed. Re-enter keys via Settings or .env.")
    else:
        print("\nDry run only. Re-run with --apply to delete.")
    con.close()


if __name__ == "__main__":
    main()
