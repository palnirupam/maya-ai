import asyncio
import os
os.environ["MAYA_TESTING"] = "1"
from backend.api.main import app, startup_event, shutdown_event

async def test_startup():
    print("Testing startup event...")
    try:
        await startup_event()
        print("Startup event passed.")
    except Exception as e:
        print(f"Startup event CRASHED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await shutdown_event()

if __name__ == "__main__":
    asyncio.run(test_startup())
