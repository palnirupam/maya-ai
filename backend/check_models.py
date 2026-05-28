import asyncio
import sys

API_KEY = sys.argv[1] if len(sys.argv) > 1 else ""

if not API_KEY:
    print("Usage: python check_models.py YOUR_API_KEY")
    sys.exit(1)

from google import genai

async def list_models():
    client = genai.Client(api_key=API_KEY)
    print("Available Gemini models:")
    print("=" * 50)
    
    # Use await for async method
    response = await client.aio.models.list()
    
    count = 0
    for m in response:
        name = m.name
        print(f"  {name}")
        count += 1
    print(f"\nTotal: {count} models")

asyncio.run(list_models())
