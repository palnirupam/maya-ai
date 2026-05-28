"""
Maya AI — Contact Manager Tool
Handles saving contacts to SQLite and looking them up with fuzzy matching.
"""
import logging
from rapidfuzz import process, fuzz
from backend.database.connection import SessionLocal
from backend.database.models import Contact

logger = logging.getLogger(__name__)

def save_contact(name: str, phone: str) -> str:
    """
    Saves a contact with a name and phone number to the database.
    If the contact already exists, updates their phone number.
    Args:
        name (str): Name of the contact (e.g. 'Pintu', 'Soumojit').
        phone (str): Phone number of the contact.
    """
    name_clean = name.strip()
    phone_clean = phone.strip()
    
    db = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.name == name_clean).first()
        if contact:
            old_phone = contact.phone
            contact.phone = phone_clean
            db.commit()
            logger.info(f"Updated contact '{name_clean}' from {old_phone} to {phone_clean}")
            return f"SUCCESS: Updated contact '{name_clean}' with phone number: {phone_clean} (old number was: {old_phone})."
        else:
            new_contact = Contact(name=name_clean, phone=phone_clean)
            db.add(new_contact)
            db.commit()
            logger.info(f"Saved new contact '{name_clean}': {phone_clean}")
            return f"SUCCESS: Saved contact '{name_clean}' with phone number: {phone_clean}."
    except Exception as e:
        logger.error(f"Error saving contact: {e}")
        return f"ERROR: Could not save contact. {e}"
    finally:
        db.close()


def lookup_contact(name: str) -> dict:
    """
    Helper function to search for a contact using fuzzy matching.
    Returns a dict with {"name": str, "phone": str, "score": float} or None.
    """
    name_clean = name.strip().lower()
    if not name_clean:
        return None
        
    db = SessionLocal()
    try:
        contacts = db.query(Contact).all()
        if not contacts:
            return None
            
        choices = {c.name: c for c in contacts}
        # Use rapidfuzz process.extractOne to find the best match
        # It handles substrings and partial matches nicely
        match_res = process.extractOne(
            name_clean, 
            choices.keys(), 
            scorer=fuzz.partial_ratio,
            score_cutoff=75.0
        )
        
        if match_res:
            matched_name, score, _ = match_res
            contact_obj = choices[matched_name]
            return {
                "name": contact_obj.name,
                "phone": contact_obj.phone,
                "score": score
            }
        return None
    except Exception as e:
        logger.error(f"Error looking up contact: {e}")
        return None
    finally:
        db.close()


def get_contact_number(name: str) -> str:
    """
    Retrieves the phone number of a contact by name. Uses fuzzy search.
    Args:
        name (str): The name of the contact to look up (e.g. 'Pintu').
    """
    match = lookup_contact(name)
    if match:
        return f"SUCCESS: Found contact '{match['name']}' with phone number: {match['phone']} (match score: {match['score']:.1f}%)."
    return f"ERROR: No contact found matching '{name}'."
