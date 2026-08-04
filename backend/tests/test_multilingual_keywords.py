"""
Test: Multilingual keyword coverage (Banglish, English, Hindilish)
"""

import sys
sys.path.insert(0, r"c:\maya-ai\backend")

from brain.agents.agent_defs import OS_EXECUTOR_PROMPT

print("=" * 70)
print("🌍 MAYA AI — MULTILINGUAL KEYWORD COVERAGE TEST")
print("=" * 70)

# Test keywords in 3 languages
test_cases = {
    "DISLIKE (Try Alternative)": {
        "Banglish": ["valo lagche na", "pasondo hoyni", "bhalo na", "change koro"],
        "English": ["don't like", "not good", "doesn't look good", "change it", "try another"],
        "Hindilish": ["accha nahi hai", "pasand nahi", "badal do", "dusra lagao"],
    },
    "RESTORE (Previous)": {
        "Banglish": ["agerta better chilo", "age wala", "firiye dao"],
        "English": ["previous was better", "go back", "undo", "restore previous"],
        "Hindilish": ["pehla wala accha tha", "purana wala", "wapas karo"],
    },
    "SUGGEST (Show Options)": {
        "Banglish": ["suggest koro", "ki ki ache", "options dekhao"],
        "English": ["show options", "what else", "suggest something", "other themes"],
        "Hindilish": ["aur kya hai", "options dikhao", "suggest karo"],
    },
    "LIKE (Remember)": {
        "Banglish": ["sundor", "darun", "valo lagche"],
        "English": ["looks good", "I like it", "nice", "beautiful", "great"],
        "Hindilish": ["accha hai", "pasand hai", "bahut accha", "zabardast"],
    }
}

print("\n📊 Checking multilingual keyword coverage...")
print("-" * 70)

overall_found = 0
overall_total = 0

for category, languages in test_cases.items():
    print(f"\n{category}:")
    
    for lang, keywords in languages.items():
        found = sum(1 for kw in keywords if kw.lower() in OS_EXECUTOR_PROMPT.lower())
        total = len(keywords)
        overall_found += found
        overall_total += total
        
        coverage = (found * 100 // total) if total > 0 else 0
        status = "✅" if found == total else "⚠️" if found > 0 else "❌"
        
        print(f"  {status} {lang:12} {found}/{total} ({coverage}%)")
        
        # Show missing keywords
        missing = [kw for kw in keywords if kw.lower() not in OS_EXECUTOR_PROMPT.lower()]
        if missing:
            for m in missing:
                print(f"      ❌ Missing: '{m}'")

print("\n" + "=" * 70)
print(f"📊 OVERALL MULTILINGUAL COVERAGE:")
print(f"   Found: {overall_found}/{overall_total} keywords")
print(f"   Coverage: {overall_found * 100 // overall_total}%")
print("=" * 70)

# Language summary
banglish_count = sum(len(v.get("Banglish", [])) for v in test_cases.values())
english_count = sum(len(v.get("English", [])) for v in test_cases.values())
hindilish_count = sum(len(v.get("Hindilish", [])) for v in test_cases.values())

print(f"\n📋 Language Distribution:")
print(f"   Banglish:  {banglish_count} keywords")
print(f"   English:   {english_count} keywords")
print(f"   Hindilish: {hindilish_count} keywords")
print(f"   TOTAL:     {overall_total} keywords")

if overall_found == overall_total:
    print("\n✅ EXCELLENT! All 3 languages fully supported!")
else:
    print(f"\n⚠️  {overall_total - overall_found} keywords missing")
    print("LLM should still understand via semantic similarity")

print("\n" + "=" * 70)
