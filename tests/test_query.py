import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.tools.desktop.advanced.browser_tools import read_background_email

async def main():
    print("Testing custom search query...")
    res = await read_background_email(limit=1, query='FROM "google"')
    print(res[:100])

if __name__ == "__main__":
    asyncio.run(main())
