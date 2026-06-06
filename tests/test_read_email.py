import asyncio
import os
import sys

# Add Maya root to path to resolve backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.tools.desktop.advanced.browser_tools import read_background_email

async def main():
    print("Testing read_background_email...")
    
    # Test 1: Fetch 1 latest email
    print("\n--- Test 1: Fetch 1 latest email (unread_only=False) ---")
    result1 = await read_background_email(limit=1, unread_only=False)
    print(result1)

    # Test 2: Invalid Query Sanitization test
    print("\n--- Test 2: Invalid Query test ---")
    result2 = await read_background_email(limit=1, query="INVALID HACK")
    print(result2)

    # Test 3: Valid Query test
    print("\n--- Test 3: Valid Query test (FROM \"google\") ---")
    result3 = await read_background_email(limit=1, query='FROM "google"')
    print(result3)

if __name__ == "__main__":
    asyncio.run(main())
