"""
Test YouTube mode detection for BOTH foreground and background.

User wants to confirm:
1. "ami je tomar song ta yt te play kore dao" → Foreground (video)
2. "background e ami je tomar song ta chalao" → Background (audio only)
"""
from backend.brain.agents.intent_parsing import (
    parse_foreground_youtube_play_intent,
    parse_youtube_mode_answer,
)

print("=" * 70)
print("TEST: YouTube Mode Detection - Both Foreground & Background")
print("=" * 70)

test_cases = [
    # (text, expected_foreground_query, expected_mode, description)
    (
        "ami je tomar song ta yt te play kore dao",
        "ami je tomar song ta",
        "foreground",
        "DEFAULT: YouTube + play = foreground (video)"
    ),
    (
        "background e ami je tomar song ta chalao",
        None,  # "background" keyword blocks foreground detection
        "background",
        "EXPLICIT: background keyword = background (audio only)"
    ),
    (
        "YouTube te ami je tomar gaan background e chalao",
        None,  # "background" keyword blocks foreground detection
        "background",
        "EXPLICIT: background anywhere in text = background (audio only)"
    ),
    (
        "ami je tomar audio shunbo",
        None,  # No YouTube site mentioned
        "background",
        "EXPLICIT: audio/shunbo = background (no YouTube needed)"
    ),
    (
        "YouTube te video chalao",
        "video",
        "foreground",
        "EXPLICIT: video keyword = foreground"
    ),
    (
        "yt te cinema dekhao",
        "cinema",
        "foreground",
        "EXPLICIT: cinema keyword = foreground"
    ),
]

print("\n" + "=" * 70)
print("Phase 1: parse_foreground_youtube_play_intent()")
print("=" * 70)

for text, expected_query, _, description in test_cases:
    result = parse_foreground_youtube_play_intent(text)
    
    if expected_query is None:
        status = "✅" if result is None else "❌"
        expected_str = "None (not foreground)"
    else:
        status = "✅" if result and expected_query in result else "❌"
        expected_str = f"'{expected_query}'"
    
    print(f"\n{status} {description}")
    print(f"   Input: '{text}'")
    print(f"   Expected: {expected_str}")
    print(f"   Got: {result}")
    
    if expected_query is None:
        assert result is None, f"Should return None for: {text}"
    else:
        assert result and expected_query in result, f"Should contain '{expected_query}'"

print("\n" + "=" * 70)
print("Phase 2: parse_youtube_mode_answer()")
print("=" * 70)

for text, _, expected_mode, description in test_cases:
    result = parse_youtube_mode_answer(text)
    status = "✅" if result == expected_mode else "❌"
    
    print(f"\n{status} {description}")
    print(f"   Input: '{text}'")
    print(f"   Expected mode: {expected_mode}")
    print(f"   Got mode: {result}")
    
    assert result == expected_mode, f"Mode mismatch for: {text}"

print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED!")
print("=" * 70)

print("\n📋 SUMMARY:")
print("\n1. DEFAULT BEHAVIOR:")
print("   'yt te play koro' → foreground (video) ✅")
print("   'ami je tomar song ta yt te play kore dao' → foreground (video) ✅")

print("\n2. BACKGROUND OVERRIDE:")
print("   'background e chalao' → background (audio only) ✅")
print("   'ami je tomar audio shunbo' → background (audio only) ✅")
print("   'YouTube te ami je tomar background e chalao' → background (audio only) ✅")

print("\n3. EXPLICIT FOREGROUND:")
print("   'YouTube te video chalao' → foreground (video) ✅")
print("   'yt te cinema dekhao' → foreground (video) ✅")

print("\n🎯 CONCLUSION:")
print("YES! If you say 'background e chalao', it will play in background (audio only)!")
print("The 'background' keyword OVERRIDES the default foreground behavior.")
