"""
Full Integration Test for Universal Intent System
Tests real workflow behavior with intent classification
"""
import asyncio
from backend.brain.agents.universal_intent_classifier import classify_universal_intent, get_cache_stats, clear_intent_cache

async def test_suite():
    """Comprehensive test covering all major features"""
    
    print("=" * 70)
    print("FULL INTEGRATION TEST - Universal Intent System")
    print("=" * 70)
    print()
    
    clear_intent_cache()  # Start fresh
    
    test_cases = [
        # Camera & Wallpaper (Critical - prevent false positives)
        {
            "input": "wallpaper lagiye dao",
            "expect": {
                "wallpaper_change": True,
                "camera_outfit": False,
                "camera_review": False
            },
            "category": "Visual - Wallpaper"
        },
        {
            "input": "Srikrishna er wallpaper set koro",
            "expect": {
                "wallpaper_change": True,
                "camera_outfit": False
            },
            "category": "Visual - Wallpaper"
        },
        {
            "input": "ami kemon lagchi",
            "expect": {
                "camera_outfit": True,
                "wallpaper_change": False
            },
            "category": "Visual - Camera Outfit"
        },
        {
            "input": "outfit kemon lagche",
            "expect": {
                "camera_outfit": True,
                "wallpaper_change": False
            },
            "category": "Visual - Camera Outfit"
        },
        
        # Communication
        {
            "input": "Maa ke WhatsApp e msg pathao",
            "expect": {
                "whatsapp_send": True,
                "primary_agent": "OS_EXECUTOR"
            },
            "category": "Communication - WhatsApp"
        },
        {
            "input": "email check koro",
            "expect": {
                "email_read": True,
                "primary_agent": "OS_EXECUTOR"
            },
            "category": "Communication - Email"
        },
        
        # System Control
        {
            "input": "volume 50 koro",
            "expect": {
                "volume_control": True,
                "primary_agent": "OS_EXECUTOR"
            },
            "category": "System - Volume"
        },
        {
            "input": "wifi on koro",
            "expect": {
                "wifi_control": True,
                "primary_agent": "OS_EXECUTOR"
            },
            "category": "System - WiFi"
        },
        
        # Media
        {
            "input": "gaana chalao",
            "expect": {
                "youtube_play": True,
                "primary_agent": "OS_EXECUTOR"
            },
            "category": "Media - YouTube"
        },
        {
            "input": "pause koro",
            "expect": {
                "media_control": True,
                "primary_agent": "OS_EXECUTOR"
            },
            "category": "Media - Control"
        },
        
        # Multi-Intent (Advanced)
        {
            "input": "Chrome kholo and volume 50 koro",
            "expect": {
                "app_open": True,
                "volume_control": True
            },
            "category": "Multi-Intent"
        },
        
        # Conversation
        {
            "input": "hello",
            "expect": {
                "is_greeting": True,
                "primary_agent": "CHAT"
            },
            "category": "Conversation - Greeting"
        },
        {
            "input": "time koto",
            "expect": {
                "is_question": True,
                "primary_agent": "CHAT"
            },
            "category": "Conversation - Question"
        },
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    for i, test in enumerate(test_cases, 1):
        user_input = test["input"]
        expected = test["expect"]
        category = test["category"]
        
        print(f"Test {i}/{len(test_cases)}: {category}")
        print(f"  Input: \"{user_input}\"")
        
        try:
            intent = await classify_universal_intent(user_input, use_cache=True)
            
            # Check all expected flags
            test_passed = True
            for key, expected_value in expected.items():
                actual_value = getattr(intent, key)
                if actual_value != expected_value:
                    test_passed = False
                    errors.append(f"  {category}: {key} expected {expected_value}, got {actual_value}")
                    print(f"  ❌ FAIL: {key} = {actual_value} (expected {expected_value})")
            
            if test_passed:
                passed += 1
                print(f"  ✅ PASS")
            else:
                failed += 1
        
        except Exception as e:
            failed += 1
            error_msg = f"  {category}: Exception - {str(e)}"
            errors.append(error_msg)
            print(f"  ❌ ERROR: {e}")
        
        print()
    
    # Cache statistics
    stats = get_cache_stats()
    print("=" * 70)
    print("CACHE PERFORMANCE")
    print("=" * 70)
    print(f"Cache hits: {stats['hits']}")
    print(f"Cache misses: {stats['misses']}")
    print(f"Cache size: {stats['size']}")
    print(f"Hit rate: {stats['hit_rate']:.1%}")
    print()
    
    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total tests: {len(test_cases)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    print(f"Success rate: {passed/len(test_cases)*100:.1f}%")
    print()
    
    if errors:
        print("ERRORS:")
        for error in errors:
            print(error)
        print()
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! Integration successful!")
        return True
    else:
        print("⚠️  Some tests failed. Review errors above.")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_suite())
    exit(0 if success else 1)
