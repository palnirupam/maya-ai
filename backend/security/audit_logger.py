import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config.runtime_paths import PROJECT_ROOT, runtime_path

logger = logging.getLogger(__name__)

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bot_token",
    "cookie",
    "credential",
    "elevenlabs_key",
    "gemini_key",
    "passwd",
    "password",
    "pwd",
    "secret",
    "token",
}
_PRIVATE_MESSAGE_TOOLS = {
    "channel",
    "configure_gmail_credentials",
    "gmail_action",
    "permanent_delete_email",
    "read_background_email",
    "send_background_email",
    "trash_background_email",
    "whatsapp_send_file",
    "whatsapp_send_message",
    "whatsapp_send_multiple_files",
}
_PRIVATE_MESSAGE_KEYS = {"body", "content", "message", "text"}
_PRIVATE_EMAIL_KEYS = {"attachment_path", "email", "from_sender", "subject", "to_recipient"}
_INLINE_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|password|secret|token)(\s*[:=]\s*)([^\s;&|]+)"
)


def _is_secret_key(key: str) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in _SECRET_KEYS or normalized.endswith(
        ("_api_key", "_password", "_secret", "_token")
    )


def _private_value(value: Any) -> str:
    raw = str(value)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"<redacted sha256={digest} chars={len(raw)}>"


def _redact_payload(value: Any, *, tool_name: str = "", key: str = "") -> Any:
    """Return a JSON-safe audit copy with credentials and private messages removed."""
    if key and _is_secret_key(key):
        return "<redacted>"
    is_private_email_field = (
        key.lower() in _PRIVATE_EMAIL_KEYS and tool_name in _PRIVATE_MESSAGE_TOOLS
    )
    is_private_message_field = (
        key.lower() in _PRIVATE_MESSAGE_KEYS
        and (tool_name in _PRIVATE_MESSAGE_TOOLS or "__" in tool_name)
    )
    if (is_private_email_field or is_private_message_field) and value not in (None, ""):
        return _private_value(value)
    if isinstance(value, dict):
        return {
            str(child_key): _redact_payload(
                child_value,
                tool_name=tool_name,
                key=str(child_key),
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_payload(item, tool_name=tool_name) for item in value]
    if isinstance(value, str):
        return _INLINE_SECRET_RE.sub(r"\1\2<redacted>", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def redact_approval_payload(payload: dict, tool_name: str) -> dict:
    """Return the persistence-safe version of an approval payload."""
    redacted = _redact_payload(payload or {}, tool_name=str(tool_name).strip().lower())
    return redacted if isinstance(redacted, dict) else {}


def approval_display_payload(payload: dict, tool_name: str) -> dict:
    """Keep the target visible for approval while never displaying a credential.

    The returned object is sent to the user's currently authenticated client only;
    ``redact_approval_payload`` is used for database and audit persistence.
    """
    if not isinstance(payload, dict):
        return {}
    normalized_tool = str(tool_name).strip().lower()
    shown = dict(payload)
    if normalized_tool == "configure_gmail_credentials":
        shown["app_password"] = "<redacted>"
    elif normalized_tool == "send_background_email":
        if "body" in shown:
            shown["body"] = _private_value(shown["body"])
        if shown.get("attachment_path"):
            shown["attachment_path"] = os.path.basename(str(shown["attachment_path"]))
    return shown

class AuditLogger:
    """Writes machine-readable audit logs in JSONL format."""
    def __init__(self, log_dir: str | None = None):
        default_log_dir = runtime_path("MAYA_LOG_DIR", PROJECT_ROOT / "logs")
        self.log_dir = str(Path(log_dir).resolve()) if log_dir else str(default_log_dir)
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "audit.jsonl")

    def log_approval(self, request_id: str, tool_name: str, payload: dict, risk_level: str, approved: bool, approved_by: str, latency_ms: int):
        normalized_tool = str(tool_name).strip().lower()
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "tool": normalized_tool,
            "payload": redact_approval_payload(payload or {}, normalized_tool),
            "risk": risk_level,
            "approved": approved,
            "approved_by": approved_by,
            "approval_latency_ms": latency_ms
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

audit_logger = AuditLogger()
