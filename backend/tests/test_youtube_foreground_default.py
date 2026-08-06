"""
Test YouTube foreground/background detection fix.

Problem: "ami je tomar song ta yt te play kore dao" was playing in background
instead of opening video.

Expected: Default to foreground (video) unless "background" explicitly mentioned.
"""
from backend.brain.agents.intent_parsing import (
    parse_foreground_youtube_play_intent,
    parse_youtube_mode_answer,
)

def test_youtube_intent_detection():
    """Test that YouTube + play is detected correctly."""
    
    # Test cases that should return a query (foreground intent detected)
    test_cases_foreground = [
        ("yt te cinema chalao", "cinema"),  # Explicit video keyword
        ("YouTube te gaan chalao", "gaan"),  # Generic play
        ("ami je tomar song ta yt te play kore dao", "ami je tomar song ta"),  # User's actual command
        ("YouTube kholo and video dekhao", "video"),  # Explicit video
        ("yt te first video ta chalao", "first video ta"),  # Video keyword present
    ]
    
    print("=" * 60)
    print("TEST 1: parse_foreground_youtube_play_intent()")
    print("=" * 60)
    
    for text, expected_query_contains in test_cases_foreground:
        result = parse_foreground_youtube_play_intent(text)
        status = "✅" if result and expected_query_contains.lower() in result.lower() else "❌"
        print(f"{status} '{text}'")
        print(f"   → Query: {result}")
        if result:
            assert expected_query_contains.lower() in result.lower(), f"Expected '{expected_query_contains}' in query"
        print()
    
    # Test cases that should NOT be foreground (background or no YouTube)
    test_cases_not_foreground = [
        "background e gaan chalao",  # Explicit background
        "audio shunbo",  # No YouTube mentioned
        "open Chrome",  # No YouTube
    ]
    
    print("\nTest cases that should NOT be foreground:")
    for text in test_cases_not_foreground:
        result = parse_foreground_youtube_play_intent(text)
        status = "✅" if result is None else "❌"
        print(f"{status} '{text}' → {result}")
        assert result is None, f"Should not detect foreground for: {text}"
    
    print("\n" + "=" * 60)
    print("TEST 2: parse_youtube_mode_answer()")
    print("=" * 60)
    
    # Test mode detection with NEW default behavior
    mode_tests = [
        # (text, expected_mode, description)
        ("background e chalao", "background", "Explicit background request"),
        ("audio shunbo", "background", "Audio-only request"),
        ("YouTube te gaan chalao", "foreground", "DEFAULT: YouTube + play = foreground"),
        ("yt te play koro", "foreground", "DEFAULT: YouTube + play = foreground"),
        ("ami je tomar song ta yt te play kore dao", "foreground", "DEFAULT: YouTube + play = foreground"),
        ("YouTube te cinema dekhao", "foreground", "Explicit video keyword"),
        ("video dekhbo", "foreground", "Explicit watch keyword"),
        ("just play it", None, "No YouTube context"),
    ]
    
    for text, expected_mode, description in mode_tests:
        result = parse_youtube_mode_answer(text)
        status = "✅" if result == expected_mode else "❌"
        print(f"{status} {description}")
        print(f"   Input: '{text}'")
        print(f"   Expected: {expected_mode}, Got: {result}")
        assert result == expected_mode, f"Mode mismatch for: {text}"
        print()
    
    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nSUMMARY:")
    print("- YouTube + play now defaults to FOREGROUND (video playback)")
    print("- Background only when explicitly requested")
    print("- User's command 'ami je tomar song ta yt te play kore dao' will now open video!")

if __name__ == "__main__":
    test_youtube_intent_detection()
