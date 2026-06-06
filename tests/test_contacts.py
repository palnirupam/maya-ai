import sys
import logging
from backend.tools.desktop.advanced.contacts import save_contact, get_contact_number

# Configure basic logging for the test
logging.basicConfig(level=logging.INFO)

def test_contacts():
    print("=== Testing Contacts Implementation ===")
    
    # 1. Test invalid phone number
    print("\n1. Testing invalid phone number (too short)...")
    result = save_contact("TestUser", "123")
    print(f"Result: {result}")
    assert "ERROR" in result, "Failed to catch invalid phone"

    # 2. Test saving a valid contact
    print("\n2. Testing valid contact save...")
    result = save_contact("TestUser", "9876543210")
    print(f"Result: {result}")
    assert "SUCCESS" in result, "Failed to save valid contact"

    # 3. Test exact lookup
    print("\n3. Testing exact lookup...")
    result = get_contact_number("TestUser")
    print(f"Result: {result}")
    assert "SUCCESS" in result, "Failed to lookup exact contact"

    # 4. Test fuzzy lookup with 'Pintu' (which shouldn't falsely match 'Recipient' or 'TestUser')
    print("\n4. Testing loose lookup ('Pintu')...")
    result = get_contact_number("Pintu")
    print(f"Result: {result}")
    assert "ERROR" in result, "Fuzzy match falsely matched an unrelated name!"
    
    print("\nAll tests passed successfully!")

if __name__ == "__main__":
    test_contacts()
