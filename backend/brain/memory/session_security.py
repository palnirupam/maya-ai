"""Encryption helpers for short-lived conversation rows and raw archives."""

from __future__ import annotations

import hashlib
import hmac

from ...database.crypto import FERNET_KEY, crypto_manager


ENCRYPTED_SESSION_PREFIX = "enc:v1:"


def encrypt_session_content(content: str) -> str:
    """Return an explicitly versioned encrypted value for persistent storage."""
    text = str(content or "")
    if not text:
        return ""
    return ENCRYPTED_SESSION_PREFIX + crypto_manager.encrypt(text)


def decrypt_session_content(stored_content: str) -> str:
    """Decrypt current values while preserving pre-encryption row compatibility."""
    stored = str(stored_content or "")
    if not stored.startswith(ENCRYPTED_SESSION_PREFIX):
        return stored

    token = stored[len(ENCRYPTED_SESSION_PREFIX):]
    plaintext = crypto_manager.decrypt(token)
    if token and not plaintext:
        raise ValueError("Stored conversation content could not be decrypted.")
    return plaintext


def opaque_session_id(session_id: str) -> str:
    """Create a stable keyed identifier safe for logs and archive filenames."""
    return hmac.new(
        FERNET_KEY,
        str(session_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]


def migrate_legacy_session_rows(db=None, session_id: str | None = None) -> int:
    """Atomically encrypt pre-v1 plaintext SessionMemory rows in place."""
    from ...database.connection import SessionLocal
    from ...database.models import SessionMemory

    owns_session = db is None
    db = db or SessionLocal()
    try:
        query = db.query(SessionMemory).filter(SessionMemory.content.isnot(None))
        if session_id is not None:
            query = query.filter(SessionMemory.session_id == session_id)

        migrated = 0
        for row in query.all():
            content = str(row.content or "")
            if not content or content.startswith(ENCRYPTED_SESSION_PREFIX):
                continue
            row.content = encrypt_session_content(content)
            migrated += 1

        if migrated:
            db.commit()
        return migrated
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()
