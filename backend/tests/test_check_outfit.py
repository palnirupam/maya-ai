"""Test 'Check my outfit' intent detection"""
import asyncio
from backend.brain.agents.universal_intent_classifier import classify_universal_intent

async def test():
    test_cases = [
        "Check my outfit",
        "ami kemon lagchi",
        "outfit kemon lagche",
        "how do I look",
    ]
    
    for text in test_cases:
        print(f"\nTesting: '{text}'")
        
        # Simulate fast-path
        text_lower = text.lower().strip()
        needs_llm = True
        
        if len(text_lower) < 100:
            if text_lower in {'hi', 'hello', 'hey', 'ok', 'okay'}:
                needs_llm = False
            elif ' and ' not in text_lower:
                if any(word in text_lower for word in ['open', 'close', 'kholo', 'bondho']):
                    if any(app in text_lower for app in ['youtube', 'chrome', 'whatsapp']):
                        needs_llm = False
        
        print(f"  Fast-path skip LLM: {not needs_llm}")
        
        if needs_llm:
            intent = await classify_universal_intent(text, use_cache=False)
            print(f"  camera_outfit: {intent.camera_outfit}")
            print(f"  camera_review: {intent.camera_review}")
            print(f"  confidence: {intent.confidence:.2f}")

asyncio.run(test())
