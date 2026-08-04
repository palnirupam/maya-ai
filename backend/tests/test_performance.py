"""Test performance of fast-path vs LLM path"""
import asyncio
import time
from backend.brain.agents.universal_intent_classifier import classify_universal_intent, clear_intent_cache

async def test_performance():
    clear_intent_cache()
    
    test_cases = [
        # Fast-path (should be instant)
        ("Open YouTube", "Fast-path (app command)"),
        ("Chrome kholo", "Fast-path (app command)"),
        ("wallpaper lagao", "Fast-path (wallpaper keyword)"),
        ("hello", "Fast-path (greeting)"),
        ("ok", "Fast-path (short)"),
        
        # LLM path (complex queries)
        ("ami kemon lagchi", "LLM (camera outfit)"),
        ("Maa ke WhatsApp e msg pathao", "LLM (communication)"),
        ("volume 50 koro and Chrome kholo", "LLM (multi-intent)"),
    ]
    
    print("=" * 70)
    print("PERFORMANCE TEST - Fast-Path vs LLM")
    print("=" * 70)
    print()
    
    for text, category in test_cases:
        start = time.time()
        
        # Simulate fast-path logic
        text_lower = text.lower().strip()
        needs_llm = True
        
        if len(text_lower) < 100:
            if text_lower in {'hi', 'hello', 'hey', 'ok', 'okay', 'hmm', 'yes', 'no'}:
                needs_llm = False
            elif any(word in text_lower for word in ['open', 'close', 'kholo', 'bondho']):
                if any(app in text_lower for app in ['youtube', 'chrome', 'whatsapp', 'notepad', 'yt']):
                    needs_llm = False
            elif any(kw in text_lower for kw in ['wallpaper', 'background', 'desktop theme']):
                needs_llm = False
        
        if needs_llm:
            intent = await classify_universal_intent(text, use_cache=True)
            elapsed = (time.time() - start) * 1000  # ms
            path = "LLM"
        else:
            elapsed = (time.time() - start) * 1000  # ms
            path = "Fast-path"
        
        status = "✅" if elapsed < 50 else "⚠️" if elapsed < 200 else "❌"
        print(f"{status} {category}")
        print(f"   Input: \"{text}\"")
        print(f"   Path: {path}, Time: {elapsed:.1f}ms")
        print()
    
    print("=" * 70)
    print("TARGET: Fast-path <10ms, LLM first call <300ms, cached <50ms")
    print("=" * 70)

asyncio.run(test_performance())
