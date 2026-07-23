"""Local transport and WebSocket input guards for the desktop API."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import os
import uuid
from typing import Any


_DEFAULT_TRUSTED_ORIGINS = {
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
}

TRUSTED_ORIGINS = frozenset(
    origin.strip().rstrip("/")
    for origin in (
        *_DEFAULT_TRUSTED_ORIGINS,
        *(os.getenv("MAYA_ALLOWED_ORIGINS", "").split(",")),
    )
    if origin.strip()
)

MAX_WS_MESSAGE_CHARS = 16 * 1024 * 1024
MAX_TEXT_MESSAGE_CHARS = 20_000
MAX_AUDIO_BASE64_CHARS = 14 * 1024 * 1024
ALLOWED_WS_EVENTS = frozenset(
    {
        "audio_chunk",
        "audio_end",
        "text_message",
        "user_interrupted",
        "tool_approval_response",
    }
)


class ClientMessageError(ValueError):
    """A client message failed the WebSocket protocol or size policy."""


def is_loopback_host(host: str | None) -> bool:
    """Return True only for loopback IPs (plus the pytest test client)."""
    if not host:
        return False
    if os.getenv("MAYA_TESTING") == "1" and host.lower() == "testclient":
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
        if address.is_loopback:
            return True
        mapped = getattr(address, "ipv4_mapped", None)
        return bool(mapped and mapped.is_loopback)
    except ValueError:
        return False


def is_trusted_origin(origin: str | None) -> bool:
    """Match an Origin header exactly; wildcard origins are never accepted."""
    if not origin:
        return False
    return origin.strip().rstrip("/") in TRUSTED_ORIGINS


def http_boundary_error(client_host: str | None, origin: str | None) -> str | None:
    """Return a public-safe rejection reason for an HTTP request, if any."""
    if not is_loopback_host(client_host):
        return "Local API access is restricted to this computer."
    if origin and not is_trusted_origin(origin):
        return "Untrusted browser origin."
    return None


def websocket_boundary_error(client_host: str | None, origin: str | None) -> str | None:
    """Return a rejection reason for a WebSocket handshake, if any."""
    if not is_loopback_host(client_host):
        return "WebSocket access is restricted to this computer."
    if not is_trusted_origin(origin):
        return "Untrusted WebSocket origin."
    return None


def parse_client_event(raw_message: str) -> tuple[str, dict[str, Any]]:
    """Parse and validate the small JSON protocol used by the frontend."""
    if not isinstance(raw_message, str) or len(raw_message) > MAX_WS_MESSAGE_CHARS:
        raise ClientMessageError("WebSocket message is too large.")
    try:
        event = json.loads(raw_message)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ClientMessageError("Malformed WebSocket message.") from exc
    if not isinstance(event, dict):
        raise ClientMessageError("WebSocket message must be an object.")

    event_type = event.get("type")
    payload = event.get("data", {})
    if event_type not in ALLOWED_WS_EVENTS:
        raise ClientMessageError("Unsupported WebSocket event.")
    if not isinstance(payload, dict):
        raise ClientMessageError("WebSocket event data must be an object.")

    if event_type == "text_message":
        text = payload.get("text", "")
        if not isinstance(text, str) or len(text) > MAX_TEXT_MESSAGE_CHARS:
            raise ClientMessageError("Text message is too large.")

    elif event_type == "audio_end":
        audio = payload.get("audio", "")
        if not isinstance(audio, str) or len(audio) > MAX_AUDIO_BASE64_CHARS:
            raise ClientMessageError("Audio payload is too large.")
        if audio:
            try:
                base64.b64decode(audio, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ClientMessageError("Invalid audio payload.") from exc

    elif event_type == "tool_approval_response":
        request_id = payload.get("request_id")
        approved = payload.get("approved")
        if not isinstance(request_id, str) or len(request_id) > 64:
            raise ClientMessageError("Invalid approval request id.")
        try:
            uuid.UUID(request_id)
        except (ValueError, AttributeError) as exc:
            raise ClientMessageError("Invalid approval request id.") from exc
        if not isinstance(approved, bool):
            raise ClientMessageError("Approval value must be boolean.")

    return event_type, payload
