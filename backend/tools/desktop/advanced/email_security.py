"""Validation and redaction helpers for Gmail-backed tools.

This module deliberately contains no network calls.  Keeping input, attachment,
and IMAP-target validation separate from the transport makes the destructive
email paths fail closed before a server request is made.
"""

from __future__ import annotations

import os
import re
import stat
from email.header import decode_header
from email.utils import parseaddr
from typing import Any

from backend.tools.unified.core.policy import is_safe_path, is_sensitive_path


MAX_EMAIL_SUBJECT_CHARS = 255
MAX_EMAIL_BODY_CHARS = 100_000
MAX_ATTACHMENT_BYTES = 18 * 1024 * 1024
MAX_EMAIL_READ_CHARS = 12_000
MAX_EMAIL_ITEM_CHARS = 6_000

_EMAIL_RE = re.compile(
    r"(?=.{1,254}\Z)(?=.{1,64}@)[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}\Z",
    re.IGNORECASE,
)
_UID_RE = re.compile(r"[1-9][0-9]{0,19}\Z")
_QUERY_RE = re.compile(
    r'(?:(?:UNSEEN|ALL)|(?:FROM|SUBJECT|TO)\s+"[^"\r\n]{1,254}")'
    r'(?:\s+(?:(?:UNSEEN|ALL)|(?:FROM|SUBJECT|TO)\s+"[^"\r\n]{1,254}"))*\Z',
    re.IGNORECASE,
)


def _has_control_characters(value: str) -> bool:
    return "\r" in value or "\n" in value or "\x00" in value


def validate_email_address(value: Any) -> tuple[str | None, str | None]:
    """Accept one plain mailbox address, never a display name or recipient list."""
    if not isinstance(value, str):
        return None, "Recipient email address is required."
    address = value.strip()
    if not address or _has_control_characters(address) or any(char in address for char in ",;"):
        return None, "Recipient must be one valid email address."
    _, parsed = parseaddr(address)
    if parsed != address or not _EMAIL_RE.fullmatch(address):
        return None, "Recipient must be one valid email address."
    return address, None


def validate_outbound_email(
    to_recipient: Any,
    subject: Any,
    body: Any,
) -> tuple[tuple[str, str, str] | None, str | None]:
    recipient, recipient_error = validate_email_address(to_recipient)
    if recipient_error:
        return None, recipient_error
    if not isinstance(subject, str) or not subject.strip():
        return None, "Email subject is required."
    if _has_control_characters(subject) or len(subject) > MAX_EMAIL_SUBJECT_CHARS:
        return None, f"Email subject must be 1-{MAX_EMAIL_SUBJECT_CHARS} characters without line breaks."
    if not isinstance(body, str) or not body.strip():
        return None, "Email body is required."
    if "\x00" in body or len(body) > MAX_EMAIL_BODY_CHARS:
        return None, f"Email body must be 1-{MAX_EMAIL_BODY_CHARS} characters."
    return (recipient, subject.strip(), body), None


def validate_gmail_credentials(email: Any, app_password: Any) -> tuple[tuple[str, str] | None, str | None]:
    address, address_error = validate_email_address(email)
    if address_error:
        return None, "A valid Gmail address is required."
    if not address.lower().endswith("@gmail.com"):
        return None, "A Gmail address is required for this mail provider."
    if not isinstance(app_password, str):
        return None, "A valid Gmail App Password is required."
    password = "".join(app_password.split())
    if not re.fullmatch(r"[A-Za-z0-9]{16}", password):
        return None, "Gmail App Password must contain exactly 16 letters or digits."
    return (address.lower(), password), None


def validate_imap_target(uid: Any, subject: Any, from_sender: Any) -> tuple[tuple[str, str, str] | None, str | None]:
    if not isinstance(uid, str) or not _UID_RE.fullmatch(uid.strip()):
        return None, "A valid email UID is required. Read the email list again before changing it."
    if not isinstance(subject, str) or not subject.strip() or _has_control_characters(subject):
        return None, "The exact email subject is required before changing it."
    if not isinstance(from_sender, str) or not from_sender.strip() or _has_control_characters(from_sender):
        return None, "The exact email sender is required before changing it."
    if len(subject) > 998 or len(from_sender) > 998:
        return None, "The email target details are too long. Read the email list again."
    return (uid.strip(), subject.strip(), from_sender.strip()), None


def validate_imap_query(query: Any) -> tuple[str | None, str | None]:
    if not isinstance(query, str) or not query.strip() or len(query) > 1024:
        return None, "Email search query is invalid."
    candidate = query.strip()
    if not _QUERY_RE.fullmatch(candidate):
        return None, "Email search query is invalid."
    return candidate, None


def decode_mime_header(value: Any, fallback: str) -> str:
    """Decode every RFC 2047 fragment and remove line-break injection chars."""
    if value is None:
        return fallback
    chunks: list[str] = []
    try:
        parts = decode_header(str(value))
    except Exception:
        return fallback
    for part, encoding in parts:
        if isinstance(part, bytes):
            try:
                chunks.append(part.decode(encoding or "utf-8", errors="replace"))
            except (LookupError, UnicodeError):
                chunks.append(part.decode("utf-8", errors="replace"))
        else:
            chunks.append(str(part))
    decoded = "".join(chunks).replace("\r", " ").replace("\n", " ").strip()
    return decoded or fallback


def exact_header_match(expected: str, actual: str) -> bool:
    """Compare an email target exactly while tolerating harmless whitespace."""
    normalize = lambda value: " ".join(value.split()).casefold()
    return normalize(expected) == normalize(actual)


def validate_attachment_path(file_path: Any) -> tuple[str | None, str | None]:
    """Resolve one regular, non-sensitive attachment outside protected paths."""
    if not isinstance(file_path, str) or not file_path.strip():
        return None, "Attachment path is required."
    try:
        resolved = os.path.realpath(os.path.abspath(file_path))
        file_stat = os.stat(resolved)
    except OSError:
        return None, "Attachment file does not exist."
    if not stat.S_ISREG(file_stat.st_mode):
        return None, "Attachment must be a regular file."
    uploads_root = os.path.realpath(os.path.abspath("data/uploads"))
    try:
        uploaded_by_user = os.path.commonpath((resolved, uploads_root)) == uploads_root
    except ValueError:
        uploaded_by_user = False
    if is_sensitive_path(resolved) or (not is_safe_path(resolved) and not uploaded_by_user):
        return None, "Attachment path is protected."
    if file_stat.st_size > MAX_ATTACHMENT_BYTES:
        return None, f"Attachment exceeds the {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB email limit."
    return resolved, None


def read_attachment_bytes(path: str) -> tuple[bytes | None, str | None]:
    """Read a validated attachment with a second size check against file races."""
    try:
        with open(path, "rb") as handle:
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                return None, "Attachment must be a regular file."
            if file_stat.st_size > MAX_ATTACHMENT_BYTES:
                return None, f"Attachment exceeds the {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB email limit."
            payload = handle.read(MAX_ATTACHMENT_BYTES + 1)
    except OSError:
        return None, "Attachment could not be read."
    if len(payload) > MAX_ATTACHMENT_BYTES:
        return None, f"Attachment exceeds the {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB email limit."
    return payload, None


def truncate_untrusted_email_content(value: Any, limit: int = MAX_EMAIL_ITEM_CHARS) -> str:
    text = str(value or "").replace("\x00", "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[Email content truncated for safety.]"


def supports_uidplus(mail: Any) -> bool:
    try:
        status, response = mail.capability()
    except Exception:
        return False
    if str(status).upper() != "OK":
        return False
    values = response or []
    combined = b" ".join(
        item if isinstance(item, bytes) else str(item).encode("utf-8", errors="ignore")
        for item in values
        if item is not None
    )
    return b"UIDPLUS" in combined.upper().split()


def imap_uid_exists(mail: Any, uid: str) -> bool | None:
    """Return True/False after a fetch, or None when the server cannot verify state."""
    try:
        status, payload = mail.uid("FETCH", uid.encode("ascii"), "(UID)")
    except Exception:
        return None
    if str(status).upper() != "OK":
        return False
    if not payload:
        return False
    return any(item not in (None, b"", "") for item in payload)
