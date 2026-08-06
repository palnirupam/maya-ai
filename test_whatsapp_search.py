"""
Test script for WhatsApp search functionality.
Verifies that contact search works properly.
"""

import time
from backend.tools.desktop.advanced.system_tools import (
    _open_and_focus_whatsapp,
    _whatsapp_navigate_to_contact,
)


def test_whatsapp_search(contact_name: str = "Mama"):
    """Test WhatsApp contact search."""
    print("\n" + "="*60)
    print(f"Testing WhatsApp Search for: {contact_name}")
    print("="*60)
    
    # Step 1: Open WhatsApp
    print("\n[Step 1] Opening WhatsApp Desktop...")
    try:
        _open_and_focus_whatsapp()
        print("✓ WhatsApp opened successfully")
        time.sleep(2)  # Give it time to fully load
    except Exception as e:
        print(f"✗ Failed to open WhatsApp: {e}")
        return False
    
    # Step 2: Search for contact
    print(f"\n[Step 2] Searching for contact: '{contact_name}'...")
    result = _whatsapp_navigate_to_contact(contact_name)
    
    if result.startswith("SUCCESS"):
        print(f"✓ {result}")
        return True
    else:
        print(f"✗ {result}")
        return False


def test_multiple_contacts():
    """Test searching for multiple contacts."""
    test_contacts = [
        "Mama",
        "Baba",
        "Test",  # This might fail if contact doesn't exist
    ]
    
    print("\n" + "="*60)
    print("Testing Multiple Contact Searches")
    print("="*60)
    
    results = {}
    for contact in test_contacts:
        print(f"\n--- Testing: {contact} ---")
        try:
            success = test_whatsapp_search(contact)
            results[contact] = "✓ Success" if success else "✗ Failed"
            time.sleep(3)  # Wait between tests
        except Exception as e:
            results[contact] = f"✗ Error: {e}"
    
    # Summary
    print("\n" + "="*60)
    print("Test Results Summary")
    print("="*60)
    for contact, result in results.items():
        print(f"{contact:20} → {result}")
    print("="*60)


if __name__ == "__main__":
    import sys
    
    # Check if contact name provided as argument
    if len(sys.argv) > 1:
        contact = " ".join(sys.argv[1:])
        test_whatsapp_search(contact)
    else:
        # Default: test with "Mama"
        print("\n💡 Usage: python test_whatsapp_search.py <contact_name>")
        print("   Example: python test_whatsapp_search.py Mama")
        print("\n🔍 Running default test with 'Mama'...\n")
        
        success = test_whatsapp_search("Mama")
        
        if success:
            print("\n✅ Test PASSED! Contact search is working.")
        else:
            print("\n❌ Test FAILED! Check the error messages above.")
            print("\n🔧 Troubleshooting:")
            print("   1. Make sure WhatsApp Desktop is installed")
            print("   2. Make sure you're logged in to WhatsApp")
            print("   3. Make sure the contact 'Mama' exists in your contacts")
            print("   4. Try manually: Open WhatsApp → Press Ctrl+E → Type 'Mama'")
