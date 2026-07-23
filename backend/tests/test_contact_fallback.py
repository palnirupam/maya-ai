"""Unit tests for the WhatsApp synced-contacts fallback in get_contact_number.

The "Pintu bug", part 2: the OS_EXECUTOR prompt tells the model to call
get_contact_number(name) first, but that tool only searched Maya's own DB and
returned ERROR for anyone never save_contact-ed — so the send flow died even
though the resolution feature (Maya DB -> WhatsApp synced contacts) already
existed inside whatsapp_send_message. get_contact_number must use the same
resolution chain.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import json
from unittest.mock import patch

from backend.tools.desktop.advanced import contacts
from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager


def _wa(connected=True, resolved=None, raises=None):
    """Patch the whatsapp_manager singleton for one test."""
    patches = [
        patch.object(whatsapp_manager, "start", lambda: None),
        patch.object(whatsapp_manager, "wait_for_connected", lambda *_a, **_k: connected),
    ]
    if raises is not None:
        patches.append(patch.object(
            whatsapp_manager, "resolve_contact",
            side_effect=raises, create=False,
        ))
    else:
        patches.append(patch.object(
            whatsapp_manager, "resolve_contact",
            lambda name, **_kwargs: resolved if resolved is not None else {"success": False, "error": "not found"},
        ))
    return patches


def _run(name, db_match, wa_patches):
    with patch.object(contacts, "lookup_contact", lambda _n: db_match):
        started = [p.start() for p in wa_patches]
        try:
            return contacts.get_contact_number(name)
        finally:
            for p in wa_patches:
                p.stop()


def test_maya_db_hit_short_circuits_without_whatsapp():
    def boom(_name):
        raise AssertionError("resolve_contact must not be called on a DB hit")

    result = _run(
        "Pintu",
        {"name": "Pintu", "phone": "919876543210", "score": 100.0},
        [patch.object(whatsapp_manager, "resolve_contact", boom)],
    )
    assert result.startswith("SUCCESS")
    assert "919876543210" in result


def test_db_miss_resolves_from_whatsapp_synced_contacts():
    # The exact Pintu scenario: not in Maya's DB, unique match in the
    # logged-in WhatsApp account's contacts.
    result = _run("Pintu", None, _wa(resolved={
        "success": True,
        "name": "Pintu Da",
        "phone": "919812345678",
        "candidates": [{"name": "Pintu Da", "number": "919812345678", "score": 3}],
    }))
    assert result.startswith("SUCCESS")
    assert "919812345678" in result
    assert "WhatsApp" in result


def test_db_miss_multiple_whatsapp_matches_returns_pick_list():
    result = _run("Pintu", None, _wa(resolved={
        "success": True,
        "name": "Pintu Da",
        "phone": "919812345678",
        "candidates": [
            {"name": "Pintu Da", "number": "919812345678", "score": 3},
            {"name": "Pintu Kaku", "number": "919811112222", "score": 3},
        ],
    }))
    assert result.startswith("CLARIFICATION_NEEDED:")
    payload = json.loads(result[len("CLARIFICATION_NEEDED:"):])
    assert payload["kind"] == "contact_pick"
    assert [c["name"] for c in payload["candidates"]] == ["Pintu Da", "Pintu Kaku"]


def test_whatsapp_not_connected_fails_fast_and_honest():
    calls = []
    wa_patches = [
        patch.object(
            whatsapp_manager,
            "resolve_contact",
            lambda name, **kwargs: calls.append((name, kwargs)) or {
                "success": False,
                "error": "WhatsApp is not connected.",
            },
        ),
    ]
    result = _run("Pintu", None, wa_patches)
    assert result.startswith("ERROR")
    assert "not connected" in result
    assert calls == [("Pintu", {"wait_timeout": contacts._WA_LOOKUP_WAIT_SECONDS})]


def test_whatsapp_miss_reports_both_sources_searched():
    result = _run("Pintu", None, _wa(resolved={"success": False, "error": "not found"}))
    assert result.startswith("ERROR")
    assert "WhatsApp" in result


def test_whatsapp_error_degrades_to_plain_error():
    result = _run("Pintu", None, _wa(raises=RuntimeError("service exploded")))
    assert result.startswith("ERROR")


def test_zero_candidates_uses_top_level_resolution():
    # Older service responses may omit candidates — the top-level name/phone
    # must still resolve.
    result = _run("Pintu", None, _wa(resolved={
        "success": True, "name": "Pintu", "phone": "919812345678", "candidates": [],
    }))
    assert result.startswith("SUCCESS")
    assert "919812345678" in result
