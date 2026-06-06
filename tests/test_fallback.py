import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO)

from backend.brain.providers.fallback import fallback_manager

async def test_fallback():
    models_to_try = ["gemini-pro", "gemini-flash", "gemini-lite"]

    print("\n--- Test 1: Initial State ---")
    available = fallback_manager.get_available_models(models_to_try)
    print(f"Available models: {available}")
    assert available == models_to_try, "All models should be available initially"

    print("\n--- Test 2: Simulating 'gemini-pro' 503 Error ---")
    # Simulate marking gemini-pro as failed
    fallback_manager.mark_failed("gemini-pro", "HTTP 503 Service Unavailable")

    available = fallback_manager.get_available_models(models_to_try)
    print(f"Available models after failure: {available}")
    assert "gemini-pro" not in available, "gemini-pro should be in cooldown"
    assert available[0] == "gemini-flash", "gemini-flash should be the new primary"

    print("\n--- Test 3: Cooldown Expiration ---")
    # Manually reduce cooldown time to 1 second for testing
    fallback_manager._cooldowns["gemini-pro"] = time.time() + 1
    
    print("Waiting 1.5 seconds for cooldown to expire...")
    await asyncio.sleep(1.5)
    
    available = fallback_manager.get_available_models(models_to_try)
    print(f"Available models after cooldown: {available}")
    assert "gemini-pro" in available, "gemini-pro should be back online"
    
    print("\n✅ Auto Fallback Logic Works Perfectly!")

if __name__ == "__main__":
    asyncio.run(test_fallback())
