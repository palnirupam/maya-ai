"""
Maya AI — Contact Manager Tool
Handles saving contacts to SQLite and looking them up with fuzzy matching,
falling back to the logged-in WhatsApp account's synced contacts.
"""
import json
import re
import logging
from rapidfuzz import process, fuzz
from sqlalchemy import func
from backend.database.connection import SessionLocal
from backend.database.models import Contact

logger = logging.getLogger(__name__)

# Bounded wait for the WhatsApp service before the synced-contacts fallback.
# The send tools tolerate 90s, but a mere lookup should fail fast and honest
# ("WhatsApp not connected") instead of hanging the whole agent turn.
_WA_LOOKUP_WAIT_SECONDS = 20


def _is_valid_phone(phone: str) -> bool:
    """ITU-T E.164 standard — 7 to 15 digits."""
    digits = re.sub(r'\D', '', phone)
    return 7 <= len(digits) <= 15


def save_contact(name: str, phone: str) -> str:
    """
    Saves a contact with a name and phone number to the database.
    If the contact already exists (case-insensitive), updates their phone number.
    Args:
        name (str): Name of the contact (e.g. 'Pintu', 'Soumojit').
        phone (str): Phone number of the contact.
    """
    name_clean = name.strip()
    phone_clean = phone.strip()

    # ── Validation ──────────────────────────────────────────────
    if not name_clean:
        return "ERROR: Contact name cannot be empty."
    if not _is_valid_phone(phone_clean):
        return f"ERROR: '{phone}' does not look like a valid phone number."

    db = SessionLocal()
    try:
        # Case-insensitive duplicate check
        contact = db.query(Contact).filter(
            func.lower(Contact.name) == name_clean.lower()
        ).first()

        if contact:
            old_phone = contact.phone
            contact.phone = phone_clean
            db.commit()
            logger.info(
                f"Updated contact '{name_clean}' "
                f"...{old_phone[-4:]} → ...{phone_clean[-4:]}"
            )
            return (
                f"SUCCESS: Updated contact '{contact.name}' "
                f"with phone number: {phone_clean} "
                f"(old number was: {old_phone}). "
                f"⚠️ If this is a different person named '{name_clean}', "
                f"please use a unique name (e.g. '{name_clean} Sharma')."
            )
        else:
            new_contact = Contact(name=name_clean, phone=phone_clean)
            db.add(new_contact)
            db.commit()
            logger.info(
                f"Saved new contact '{name_clean}': ...{phone_clean[-4:]}"
            )
            return (
                f"SUCCESS: Saved contact '{name_clean}' "
                f"with phone number: {phone_clean}."
            )

    except Exception as e:
        db.rollback()
        logger.error(f"Error saving contact '{name_clean}': {e}")
        return f"ERROR: Could not save contact. {e}"
    finally:
        db.close()


def lookup_contact(name: str) -> dict:
    """
    Helper function to search for a contact using fuzzy matching.
    Returns a dict with {"name": str, "phone": str, "score": float} or None.

    Case-insensitive. Uses WRatio scorer with cutoff 85.0 to prevent
    false positives (e.g. 'Pintu' matching 'Recipient').
    """
    name_clean = name.strip().lower()
    if not name_clean:
        return None

    db = SessionLocal()
    try:
        contacts = db.query(Contact).all()
        if not contacts:
            return None

        # Key: lowercase for matching, Value: original Contact object
        # contact_obj.name preserves original casing in the return value
        choices = {c.name.lower(): c for c in contacts}

        match_res = process.extractOne(
            name_clean,
            choices.keys(),
            scorer=fuzz.WRatio,
            score_cutoff=85.0
        )

        if match_res:
            matched_key, score, _ = match_res
            contact_obj = choices[matched_key]
            return {
                "name": contact_obj.name,  # original casing preserved
                "phone": contact_obj.phone,
                "score": score
            }
        return None

    except Exception as e:
        logger.error(f"Error looking up contact '{name}': {e}")
        return None
    finally:
        db.close()


def _lookup_whatsapp_contact(name: str) -> str:
    """Fallback when Maya's DB has no match: search the contacts synced from
    the logged-in WhatsApp account — the same resolution whatsapp_send_message
    uses — so a 'Pintu' who was never save_contact-ed is still findable.

    Returns the same string protocol as get_contact_number (SUCCESS/ERROR),
    plus CLARIFICATION_NEEDED:contact_pick when several contacts match
    (agent_team relays that list to the user verbatim)."""
    from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager

    try:
        resolved = whatsapp_manager.resolve_contact(
            name,
            wait_timeout=_WA_LOOKUP_WAIT_SECONDS,
        )
    except Exception as e:
        logger.error(f"WhatsApp synced-contact fallback failed for '{name}': {e}")
        return f"ERROR: No contact found matching '{name}' in Maya's saved contacts."

    error = resolved.get("error", "")
    if not resolved.get("success"):
        if "not connected" in error.lower():
            return (
                f"ERROR: '{name}' is not in Maya's saved contacts, and WhatsApp "
                f"is not connected, so its synced contacts could not be searched. "
                f"Ask the user for the phone number, or to pair WhatsApp first."
            )
        return (
            f"ERROR: No contact found matching '{name}' — searched Maya's "
            f"saved contacts and the WhatsApp synced contacts."
        )

    candidates = resolved.get("candidates") or []
    if len(candidates) > 1:
        payload = json.dumps(
            {
                "kind": "contact_pick",
                "query": name,
                "candidates": [
                    {"name": c.get("name", "?"), "number": c.get("number", "?")}
                    for c in candidates
                ],
            },
            ensure_ascii=False,
        )
        return f"CLARIFICATION_NEEDED:{payload}"

    best = candidates[0] if candidates else {
        "name": resolved.get("name", name),
        "number": resolved.get("phone"),
    }
    phone = best.get("number")
    if not phone:
        return (
            f"ERROR: No contact found matching '{name}' — searched Maya's "
            f"saved contacts and the WhatsApp synced contacts."
        )
    return (
        f"SUCCESS: Found contact '{best.get('name', name)}' in the WhatsApp "
        f"synced contacts with phone number: {phone}."
    )


def get_contact_number(name: str) -> str:
    """
    Retrieves the phone number of a contact by name. Uses fuzzy search over
    Maya's saved contacts, then falls back to the logged-in WhatsApp
    account's synced contacts.
    Args:
        name (str): The name of the contact to look up (e.g. 'Pintu').
    """
    match = lookup_contact(name)
    if match:
        return (
            f"SUCCESS: Found contact '{match['name']}' "
            f"with phone number: {match['phone']} "
            f"(match score: {match['score']:.1f}%)."
        )
    return _lookup_whatsapp_contact(name)

def delete_contact(name: str) -> str:
    """
    Deletes a contact from the database by name (fuzzy matched).
    Args:
        name (str): The name of the contact to delete.
    """
    match = lookup_contact(name)
    if not match:
        return f"ERROR: Could not delete because no contact was found matching '{name}'."
        
    db = SessionLocal()
    try:
        # Match returns the original casing, so we can query it exactly
        contact = db.query(Contact).filter(Contact.name == match["name"]).first()
        if contact:
            db.delete(contact)
            db.commit()
            logger.info(f"Deleted contact '{match['name']}'")
            return f"SUCCESS: Contact '{match['name']}' has been permanently deleted."
        return f"ERROR: Contact '{match['name']}' found in lookup but missing in DB."
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting contact '{name}': {e}")
        return f"ERROR: Failed to delete contact. {e}"
    finally:
        db.close()
