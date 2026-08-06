"""
Crypto Self-Heal
================
Recovers data encrypted under an OLD hardware fingerprint and re-encrypts it
under the CURRENT primary key, using the MultiFernet candidate-key chain in
backend/database/crypto.py.

Safe by design:
  * Makes a timestamped backup of data/memory.db before touching anything.
  * Only rewrites a value when it (a) decrypts via some candidate key AND
    (b) is not already under the primary key. Truly-lost rows are left as-is
    and reported.
  * Idempotent: running twice does nothing the second time.

Usage (from c:\\maya-ai root):
    python backend/scripts/crypto_selfheal.py            # dry run (report only)
    python backend/scripts/crypto_selfheal.py --apply    # perform migration
"""
import sys, os, shutil, sqlite3, argparse, json
sys.path.insert(0, os.path.abspath("."))

DB = "data/memory.db"

# table -> list of encrypted text columns
ENCRYPTED_COLUMNS = {
    "user_preferences": ["value"],
    "long_term_memory": ["category", "content"],
    "scheduled_tasks":  ["name", "task_payload"],
}

# user_preferences.value is a SQLAlchemy JSON column, so its token is stored
# json.dumps-wrapped ('"gAAAA..."'). Every other encrypted column is Text with a
# bare token. Read must unwrap, and write must re-wrap, or the raw-sqlite UPDATE
# would drop a bare token into a JSON column and break the ORM's json.loads.
_JSON_COLUMNS = {("user_preferences", "value")}


def _unwrap(v):
    if isinstance(v, str):
        try:
            loaded = json.loads(v)
            if isinstance(loaded, str):
                return loaded
        except Exception:
            pass
    return v


def _backup():
    ts = _timestamp()
    dst = f"{DB}.bak-{ts}"
    shutil.copy2(DB, dst)
    return dst


def _timestamp():
    # Avoid importing time.time() indirectly failing; use sqlite for a stable stamp.
    con = sqlite3.connect(":memory:")
    val = con.execute("SELECT strftime('%Y%m%d-%H%M%S','now')").fetchone()[0]
    con.close()
    return val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write changes")
    args = ap.parse_args()

    from backend.database.crypto import crypto_manager, _primary, _multi

    print("=" * 64)
    print("CRYPTO SELF-HEAL", "(APPLY)" if args.apply else "(DRY RUN)")
    print("=" * 64)

    if args.apply:
        bak = _backup()
        print(f"[OK] Backup written: {bak}\n")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    total_recovered = total_lost = total_primary = 0

    for table, cols in ENCRYPTED_COLUMNS.items():
        # SQL dynamic table/column names validated against ENCRYPTED_COLUMNS whitelist
        # This is necessary because SQLAlchemy ORM doesn't support dynamic table/column references
        try:
            # Validate table and column names contain only safe characters (alphanumeric, underscore)
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
                logger.error(f"Invalid table name in ENCRYPTED_COLUMNS: {table}")
                continue
            for col in cols:
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
                    logger.error(f"Invalid column name in ENCRYPTED_COLUMNS: {col}")
                    continue
            
            rows = cur.execute(f"SELECT id, {', '.join(cols)} FROM {table}").fetchall()
        except Exception:
            continue  # table not present in this DB
        print(f"--- {table} ({len(rows)} rows) ---")
        for row in rows:
            for col in cols:
                is_json = (table, col) in _JSON_COLUMNS
                token = _unwrap(row[col]) if is_json else row[col]
                if not token or not isinstance(token, str) or len(token) < 20:
                    continue
                # already primary?
                try:
                    _primary.decrypt(token.encode())
                    total_primary += 1
                    continue
                except Exception:
                    pass
                # recoverable via an older candidate key?
                plain = crypto_manager.decrypt(token)
                if plain != "" or _decryptable(_multi, token):
                    new_token = crypto_manager.rotate(token)
                    total_recovered += 1
                    label = row["key"] if "key" in row.keys() else f"id={row['id']}"
                    print(f"  [RECOVER] {table}.{col} ({label})")
                    if args.apply:
                        # Re-wrap JSON columns so the ORM can still json.loads it.
                        write_val = json.dumps(new_token) if is_json else new_token
                        cur.execute(f"UPDATE {table} SET {col}=? WHERE id=?",
                                    (write_val, row["id"]))
                else:
                    total_lost += 1
                    label = row["key"] if "key" in row.keys() else f"id={row['id']}"
                    print(f"  [LOST]    {table}.{col} ({label})")

    if args.apply:
        con.commit()
    con.close()

    print("\n" + "=" * 64)
    print(f"already-current : {total_primary}")
    print(f"recovered       : {total_recovered}")
    print(f"unrecoverable   : {total_lost}")
    print("=" * 64)
    if not args.apply and total_recovered:
        print("Dry run only. Re-run with --apply to write these changes.")
    if total_lost:
        print("Unrecoverable rows were encrypted on different hardware/salt and "
              "must be re-entered (e.g. API keys via Settings).")


def _decryptable(multi, token: str) -> bool:
    try:
        multi.decrypt(token.encode())
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
