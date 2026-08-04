"""
Test: Does Maya's prompt cover all necessary feedback keywords?
"""

import sys
sys.path.insert(0, r"c:\maya-ai\backend")

# Read OS_EXECUTOR prompt
from brain.agents.agent_defs import OS_EXECUTOR_PROMPT

print("=" * 70)
print("🔍 MAYA AI — FEEDBACK KEYWORD COVERAGE TEST")
print("=" * 70)

# Test keywords for each feedback type
test_cases = {
    "DISLIKE (Try Alternative)": [
        "valo lagche na",
        "pasondo hoyni", 
        "eta na",
        "bhalo na",
        "change koro",
        "onno wallpaper dao",
        # Additional variations
        "bhalo hoyni",
        "valo na",
        "like na",
        "different wallpaper",
    ],
    "RESTORE (Previous)": [
        "agerta better chilo",
        "purano ta bhalo chilo",
        "restore koro",
        "undo koro",
        # Additional variations
        "age wala",
        "previous",
        "firiye dao",
    ],
    "SUGGEST (Show Options)": [
        "onno theme dao",
        "different type",
        "suggest koro",
        # Additional variations
        "suggestion dao",
        "ki ki ache",
        "options dekhao",
    ],
    "LIKE (Remember)": [
        "wallpaper ta sundor",
        "etake bhalo lagche",
        "perfect",
        # Additional variations
        "khub sundor",
        "darun",
        "awesome",
        "valo lagche",
    ]
}

print("\n📊 Checking keyword coverage in OS_EXECUTOR prompt...")
print("-" * 70)

total_found = 0
total_missing = 0

for category, keywords in test_cases.items():
    print(f"\n{category}:")
    found = []
    missing = []
    
    for keyword in keywords:
        if keyword.lower() in OS_EXECUTOR_PROMPT.lower():
            found.append(keyword)
            print(f"  ✅ '{keyword}'")
        else:
            missing.append(keyword)
            print(f"  ❌ '{keyword}' — NOT IN PROMPT")
    
    total_found += len(found)
    total_missing += len(missing)
    
    print(f"  Coverage: {len(found)}/{len(keywords)} ({len(found)*100//len(keywords)}%)")

print("\n" + "=" * 70)
print(f"📊 OVERALL COVERAGE: {total_found}/{total_found + total_missing} keywords")
print(f"   Found: {total_found} ✅")
print(f"   Missing: {total_missing} ❌")
print("=" * 70)

if total_missing > 0:
    print("\n⚠️  RECOMMENDATION:")
    print("Some common variations are missing from the prompt.")
    print("The LLM should still understand them via semantic similarity,")
    print("but adding more variations will improve accuracy.")
else:
    print("\n✅ All keywords covered!")

# Check for the critical instruction
if "NEVER just say \"okay\"" in OS_EXECUTOR_PROMPT:
    print("\n✅ Critical instruction found: 'NEVER just say okay'")
else:
    print("\n❌ Missing critical instruction about not giving up!")

if "ALWAYS take action" in OS_EXECUTOR_PROMPT:
    print("✅ Found: 'ALWAYS take action'")
else:
    print("❌ Missing: 'ALWAYS take action'")

print("\n" + "=" * 70)
print("🎯 CONCLUSION:")
if total_missing == 0:
    print("✅ Maya's prompt has excellent keyword coverage!")
else:
    print(f"⚠️  {total_missing} keywords missing, but semantic understanding should work")
print("=" * 70)
