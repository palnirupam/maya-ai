"""Quick test for universal intent classifier"""
import asyncio
from backend.brain.agents.universal_intent_classifier import classify_universal_intent

async def test_basic():
    print("Testing Universal Intent Classifier...\n")
    
    test_cases = [
        ("wallpaper lagiye dao", "Should detect wallpaper, NOT camera"),
        ("ami kemon lagchi", "Should detect camera outfit"),
        ("Maa ke msg pathao", "Should detect WhatsApp send"),
        ("volume 50 koro", "Should detect volume control"),
    ]
    
    for text, expected in test_cases:
        print(f"Testing: '{text}'")
        print(f"Expected: {expected}")
        try:
            intent = await classify_universal_intent(text, use_cache=False)
            print(f"✅ Result: agent={intent.primary_agent}, confidence={intent.confidence:.2f}")
            
            # Check specific flags
            if "wallpaper" in text.lower():
                print(f"   wallpaper_change={intent.wallpaper_change}, camera_outfit={intent.camera_outfit}")
            elif "kemon lagchi" in text.lower():
                print(f"   camera_outfit={intent.camera_outfit}, wallpaper_change={intent.wallpaper_change}")
            elif "msg" in text.lower():
                print(f"   whatsapp_send={intent.whatsapp_send}")
            elif "volume" in text.lower():
                print(f"   volume_control={intent.volume_control}")
            
            print()
        except Exception as e:
            print(f"❌ ERROR: {e}\n")
            import traceback
            traceback.print_exc()
            return False
    
    print("✅ All tests passed!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_basic())
    exit(0 if success else 1)
