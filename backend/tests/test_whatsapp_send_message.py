"""Unit tests for WhatsApp background send contact resolution."""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import json
from unittest.mock import patch

from backend.tools.desktop.advanced.system_tools import (
    whatsapp_send_file,
    whatsapp_send_message,
    whatsapp_send_multiple_files,
)
from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager


def test_send_message_accepts_authenticated_after_synced_contact_resolution():
    sent = []

    with patch("backend.tools.desktop.advanced.contacts.lookup_contact", return_value=None), \
         patch.object(whatsapp_manager, "resolve_contact", return_value={
             "success": True,
             "name": "Pintu Da",
             "phone": "919812345678",
             "candidates": [{"name": "Pintu Da", "number": "919812345678"}],
         }), \
         patch.object(
             whatsapp_manager,
             "send_message_receipt",
             side_effect=lambda phone, msg: sent.append((phone, msg)) or {"success": True, "status": "sent"},
         ):
        result = whatsapp_send_message("Pintu", "hi")

    assert result.startswith("SUCCESS")
    assert "Pintu Da" in result
    assert sent == [("919812345678", "hi")]


def test_raw_phone_send_accepts_authenticated_status():
    sent = []

    with patch.object(
        whatsapp_manager,
        "send_message_receipt",
        side_effect=lambda phone, msg: sent.append((phone, msg)) or {"success": True, "status": "sent"},
    ):
        result = whatsapp_send_message("9812345678", "hi")

    assert result.startswith("SUCCESS")
    assert sent == [("919812345678", "hi")]


def test_multiple_synced_contact_matches_return_pick_payload():
    with patch("backend.tools.desktop.advanced.contacts.lookup_contact", return_value=None), \
         patch.object(whatsapp_manager, "resolve_contact", return_value={
             "success": True,
             "candidates": [
                 {"name": "Pintu Da", "number": "919812345678"},
                 {"name": "Pintu Kaku", "number": "919811112222"},
             ],
         }):
        result = whatsapp_send_message("Pintu", "hi")

    assert result.startswith("CLARIFICATION_NEEDED:")
    payload = json.loads(result[len("CLARIFICATION_NEEDED:"):])
    assert payload["kind"] == "contact_pick"
    assert [c["name"] for c in payload["candidates"]] == ["Pintu Da", "Pintu Kaku"]


def test_file_send_ambiguous_contact_returns_pick_without_transport(tmp_path):
    attachment = tmp_path / "report.pdf"
    attachment.write_text("report", encoding="utf-8")
    with patch("backend.tools.desktop.advanced.contacts.lookup_contact", return_value=None), \
         patch.object(whatsapp_manager, "resolve_contact", return_value={
             "success": True,
             "candidates": [
                 {"name": "Pintu Da", "number": "919812345678"},
                 {"name": "Pintu Kaku", "number": "919811112222"},
             ],
         }), \
         patch.object(whatsapp_manager, "send_file") as send_file:
        result = whatsapp_send_file("Pintu", str(attachment))

    assert result.startswith("CLARIFICATION_NEEDED:")
    payload = json.loads(result[len("CLARIFICATION_NEEDED:"):])
    assert payload["kind"] == "contact_pick"
    send_file.assert_not_called()


def test_invalid_raw_phone_fails_before_status_or_transport():
    with patch.object(whatsapp_manager, "get_status") as status, patch.object(
        whatsapp_manager, "send_message"
    ) as send:
        result = whatsapp_send_message("1234567", "hi")

    assert result == "ERROR: Invalid WhatsApp phone number."
    status.assert_not_called()
    send.assert_not_called()


def test_text_send_does_not_preflight_fail_a_cold_background_service():
    with patch.object(whatsapp_manager, "get_status") as status, patch.object(
        whatsapp_manager,
        "send_message_receipt",
        return_value={"success": True, "status": "sent", "message_id": "m-1"},
    ) as send:
        result = whatsapp_send_message("9812345678", "hi")

    assert result == "SUCCESS: WhatsApp accepted the message for '9812345678' (919812345678). Delivery: Sent."
    status.assert_not_called()
    send.assert_called_once_with("919812345678", "hi")


def test_multiple_file_all_failed_result_has_error_prefix(tmp_path):
    first = tmp_path / "one.pdf"
    second = tmp_path / "two.pdf"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    failed = [
        {"file": str(first), "success": False, "error": "rejected"},
        {"file": str(second), "success": False, "error": "rejected"},
    ]
    with patch.object(whatsapp_manager, "get_status", return_value={"status": "connected"}), patch.object(
        whatsapp_manager, "send_files", return_value=failed
    ):
        result = whatsapp_send_multiple_files(
            "9876543210", [str(first), str(second)]
        )

    assert result.startswith("ERROR:")
    assert "0/2 files sent successfully" in result


def test_multiple_file_send_skips_a_duplicate_attachment_path(tmp_path):
    attachment = tmp_path / "report.pdf"
    attachment.write_text("report", encoding="utf-8")
    with patch.object(whatsapp_manager, "send_files", return_value=[{
        "file": str(attachment), "success": True, "messageId": "m-1"
    }]) as send:
        result = whatsapp_send_multiple_files(
            "9812345678", [str(attachment), str(attachment)]
        )

    assert send.call_count == 1
    assert len(send.call_args.args[1]) == 1
    assert "Duplicate attachment skipped" in result


def test_single_file_missing_absolute_path_is_never_fuzzy_substituted(tmp_path):
    """BUG-020: a missing absolute path must fail, not silently send a lookalike."""
    decoy = tmp_path / "quarterly report 2026.pdf"
    decoy.write_text("decoy", encoding="utf-8")
    missing = r"C:\audit-gone\quarterly report 2026.pdf"

    with patch(
        "backend.tools.desktop.advanced.system_tools._find_file_in_search_dirs",
        return_value=str(decoy),
    ) as finder, patch.object(whatsapp_manager, "send_file") as send:
        result = whatsapp_send_file("9812345678", missing)

    assert result.startswith("ERROR:")
    assert "does not exist" in result
    finder.assert_not_called()
    send.assert_not_called()


def test_multiple_file_missing_absolute_path_is_never_fuzzy_substituted(tmp_path):
    """BUG-020 (multi-file variant): missing absolute path reports not-found."""
    decoy = tmp_path / "quarterly report 2026.pdf"
    decoy.write_text("decoy", encoding="utf-8")
    missing = r"C:\audit-gone\quarterly report 2026.pdf"

    with patch(
        "backend.tools.desktop.advanced.system_tools._find_file_in_search_dirs",
        return_value=str(decoy),
    ) as finder, patch.object(whatsapp_manager, "send_files") as send:
        result = whatsapp_send_multiple_files("9812345678", [missing])

    assert result.startswith("ERROR:")
    assert "path does not exist" in result
    finder.assert_not_called()
    send.assert_not_called()


def test_multiple_file_failed_send_keeps_uploads_cache_copy(monkeypatch, tmp_path):
    """BUG-021: a FAILED multi-file send must not delete the uploads-cache copy."""
    uploads = tmp_path / "data" / "uploads"
    uploads.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    upload = uploads / "user upload.txt"
    upload.write_text("only copy", encoding="utf-8")

    failed = [{"file": str(upload), "success": False, "error": "not connected"}]
    with patch.object(whatsapp_manager, "send_files", return_value=failed):
        result = whatsapp_send_multiple_files("9812345678", [str(upload)])

    assert result.startswith("ERROR:")
    assert upload.exists()


def test_multiple_file_successful_send_still_cleans_uploads_cache_copy(monkeypatch, tmp_path):
    """Counterpart to BUG-021: a SUCCESSFUL send still removes the temp copy."""
    uploads = tmp_path / "data" / "uploads"
    uploads.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    upload = uploads / "user upload.txt"
    upload.write_text("only copy", encoding="utf-8")

    sent = [{"file": str(upload), "success": True, "messageId": "m-1"}]
    with patch.object(whatsapp_manager, "send_files", return_value=sent):
        result = whatsapp_send_multiple_files("9812345678", [str(upload)])

    assert result.startswith("SUCCESS")
    assert not upload.exists()


def test_attachment_validators_reject_link_resolving_to_sensitive_target(tmp_path):
    """Platform-independent symlink/reparse check: realpath resolution must expose
    a link that points at credential material, for BOTH attach validators."""
    from backend.tools.desktop.advanced.whatsapp_manager import (
        validate_attachment_path as wa_validate,
    )
    from backend.tools.desktop.advanced.email_security import (
        validate_attachment_path as em_validate,
    )

    secret = tmp_path / ".env"
    secret.write_text("TOKEN=secret", encoding="utf-8")
    innocent = tmp_path / "innocent.txt"
    innocent.write_text("placeholder", encoding="utf-8")

    real_realpath = os.path.realpath

    def linked_realpath(path, **kwargs):
        resolved = real_realpath(path, **kwargs)
        if resolved == real_realpath(str(innocent)):
            return real_realpath(str(secret))
        return resolved

    with patch("os.path.realpath", side_effect=linked_realpath):
        wa_resolved, wa_error = wa_validate(str(innocent))
        em_resolved, em_error = em_validate(str(innocent))

    assert wa_resolved is None and wa_error == "Attachment path is protected"
    assert em_resolved is None and em_error == "Attachment path is protected."
