"""Test wallpaper feedback intent detection"""
import asyncio
from backend.brain.agents.universal_intent_classifier import classify_universal_intent

async def test():
    test_cases = [
        "Wallpaper ta valo lagche na",
        "wallpaper valo na",
        "eta pasondo hoyni",
        "change koro wallpaper",
        "onno wallpaper dao",
    ]
    
    for text in test_cases:
        print(f"\nTesting: '{text}'")
        intent = await classify_universal_intent(text, use_cache=False)
        print(f"  wallpaper_change: {intent.wallpaper_change}")
        print(f"  is_casual_chat: {intent.is_casual_chat}")
        print(f"  primary_agent: {intent.primary_agent}")
        print(f"  confidence: {intent.confidence:.2f}")

asyncio.run(test())
