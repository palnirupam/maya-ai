# 🚀 Universal Intent System - Quick Reference

## One-Page Cheat Sheet

### 📦 Import
```python
from backend.brain.agents.universal_intent_classifier import classify_universal_intent
```

### 🔍 Basic Usage
```python
intent = await classify_universal_intent("user message", use_cache=True)
```

### 📊 IntentResult Structure
```python
intent.primary_agent        # "CHAT" | "OS_EXECUTOR" | "RESEARCHER" | "CODER"
intent.confidence          # 0.0 - 1.0
intent.entities           # {"contact_names": [...], "numbers": [...], ...}

# 30+ Boolean Flags
intent.whatsapp_send      # WhatsApp message send
intent.email_read         # Read emails
intent.camera_outfit      # Outfit review
intent.wallpaper_change   # Desktop wallpaper
intent.youtube_play       # Play video/music
intent.volume_control     # System volume
intent.file_create        # Create file
intent.app_open          # Open application
intent.web_search        # Web search
# ... 20+ more
```

### 🎯 Intent Categories

| Category | Flags | Example |
|----------|-------|---------|
| 📱 **Communication** | whatsapp_*, email_* | "Maa ke msg pathao" |
| 📷 **Visual** | camera_*, wallpaper_change | "ami kemon lagchi" |
| 🎵 **Media** | youtube_*, media_control | "gaana chalao" |
| ⚙️ **System** | volume_*, wifi_*, power_* | "volume 50 koro" |
| 📁 **Files** | file_* | "Desktop e save koro" |
| 🖥️ **Apps** | app_open, app_close | "Chrome kholo" |
| 🔍 **Research** | web_search, news_query | "Python tutorial search koro" |
| 🎨 **Widgets** | create_widget | "calculator banao" |
| 💻 **Code** | code_execution, script_create | "script run koro" |
| 💬 **Chat** | is_greeting, is_question | "hello", "time koto" |

### 💡 Common Patterns

#### Pattern 1: Single Intent
```python
intent = await classify_universal_intent("volume 50 koro")
if intent.volume_control:
    level = intent.entities["numbers"][0]  # 50
    await set_volume(level)
```

#### Pattern 2: Multi-Intent
```python
intent = await classify_universal_intent("Chrome kholo and volume 50 koro")
if intent.app_open:
    await open_app("chrome")
if intent.volume_control:
    await set_volume(50)
```

#### Pattern 3: Entity Extraction
```python
intent = await classify_universal_intent("Maa ke WhatsApp e bolo hi")
if intent.whatsapp_send:
    contact = intent.entities["contact_names"][0]  # "Maa"
    await send_whatsapp(contact, "hi")
```

#### Pattern 4: Chrome Profile
```python
intent = await classify_universal_intent("Chrome kholo Nirupam profile e")
if intent.app_open and intent.chrome_profile:
    await open_chrome_profile(intent.chrome_profile)  # "Nirupam"
```

### ⚡ Performance Tips

```python
# 1. Always use cache
intent = await classify_universal_intent(text, use_cache=True)

# 2. Check cache stats
from backend.brain.agents.universal_intent_classifier import get_cache_stats
stats = get_cache_stats()
print(f"Hit rate: {stats['hit_rate']:.1%}")

# 3. Clear cache if needed
from backend.brain.agents.universal_intent_classifier import clear_intent_cache
clear_intent_cache()
```

### 🎯 Critical Edge Cases

```python
# Wallpaper with "lagche" → Should NOT trigger camera
"wallpaper ta valo lagche na"
→ wallpaper_change=True, camera_outfit=False ✅

# Outfit review → Should NOT trigger wallpaper
"ami kemon lagchi"
→ camera_outfit=True, wallpaper_change=False ✅

# Complex multi-action
"Chrome e wallpaper download kore lagao"
→ app_open=True, wallpaper_change=True ✅
```

### 🧪 Quick Test

```python
# Run in Python
import asyncio
from backend.brain.agents.universal_intent_classifier import classify_universal_intent

async def test():
    queries = [
        "wallpaper lagiye dao",
        "ami kemon lagchi",
        "Maa ke msg pathao",
        "volume 50 koro",
    ]
    for q in queries:
        intent = await classify_universal_intent(q)
        print(f"{q} → {intent.primary_agent}")

asyncio.run(test())
```

### 📊 Monitoring

```python
from backend.brain.agents.universal_intent_classifier import get_cache_stats

def log_intent_metrics():
    stats = get_cache_stats()
    logger.info(f"""
    Intent Metrics:
    - Total queries: {stats['hits'] + stats['misses']}
    - Cache hit rate: {stats['hit_rate']:.1%}
    - Cache size: {stats['size']}
    """)
```

### 🚨 Error Handling

```python
try:
    intent = await classify_universal_intent(text)
except Exception as e:
    logger.error(f"Intent classification failed: {e}")
    # Safe fallback
    intent = IntentResult(primary_agent="CHAT", is_question=True)
```

### 🔧 Debug Mode

```python
intent = await classify_universal_intent(text, use_cache=False)
print(f"Primary: {intent.primary_agent}")
print(f"Confidence: {intent.confidence}")
print(f"Active intents: {[k for k,v in intent.__dict__.items() if isinstance(v, bool) and v]}")
print(f"Entities: {intent.entities}")
```

---

## 📁 File Locations

```
backend/brain/agents/
├── universal_intent_classifier.py  ← Main code
├── intent_classifier.py           ← Old (camera only)
└── _workflow.py                    ← Integration point

docs/
├── UNIVERSAL_INTENT_SYSTEM.md     ← Complete guide
├── MIGRATION_GUIDE.md             ← Integration steps
└── INTENT_SYSTEM_SUMMARY.md       ← Executive summary

tests/
└── test_universal_intent.py       ← Test suite
```

---

## ✅ Quick Validation

Test these to verify it's working:

```python
# Test 1: Wallpaper (should NOT trigger camera)
"Srikrishna er wallpaper lagiye dao"
→ Expected: wallpaper_change=True, camera_*=False

# Test 2: Outfit (should trigger camera)
"ami kemon lagchi"
→ Expected: camera_outfit=True, wallpaper_change=False

# Test 3: Multi-intent
"Chrome kholo and volume 50 koro"
→ Expected: app_open=True, volume_control=True

# Test 4: Entity extraction
"Maa ke WhatsApp e msg pathao"
→ Expected: whatsapp_send=True, entities={"contact_names": ["Maa"]}
```

---

**For detailed info:** See `UNIVERSAL_INTENT_SYSTEM.md`  
**For integration:** See `MIGRATION_GUIDE.md`  
**For examples:** See `test_universal_intent.py`
