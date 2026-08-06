# 🤖 Maya AI — Wallpaper Feedback Handling

## 🎯 **Scenario:**
```
User: "maya wallpaper ta valo lagche na"
User: "wallpaper ta change koro"
User: "eta pasondo hoyni"
User: "another wallpaper dao"
```

---

## 💡 **Maya's Response Strategy:**

### Option 1: Offer Alternative from Same Theme 🔄
```
User: "hacker wallpaper ta valo lagche na"

Maya Response:
"Āchha, āmi onno ekta hacker wallpaper try korchi..."
→ Downloads different hacker wallpaper (different seed/source)
→ Sets automatically
→ "Etake kemon lagche?"
```

### Option 2: Suggest Different Styles 🎨
```
User: "wallpaper ta valo lagche na"

Maya Response:
"Āchha! Ami onno kichhu suggest korchi:
1. Nature/Scenic wallpaper
2. Minimal/Clean wallpaper  
3. Dark/Cyberpunk wallpaper
4. Custom (tumi ki theme chao bolo)

Konta try kori?"
```

### Option 3: Restore Previous Wallpaper ↩️
```
User: "wallpaper ta valo lagche na, agerta better chilo"

Maya Response:
"Āchha, ami agerta firiye dichhi..."
→ Restores previous wallpaper from history
→ "Age wala wallpaper set hoye gechhe!"
```

### Option 4: Let User Choose ⚙️
```
User: "wallpaper ta valo lagche na"

Maya Response:
"Display Settings khulchhi, tumi nijeই choose koro?"
→ Opens Windows Display Settings
→ User can manually browse & select
```

---

## 🛠️ **Implementation Strategy:**

### 1. Maintain Wallpaper History
```python
# Store last 5 wallpapers in memory/database
wallpaper_history = [
    {"path": "C:/path/to/wallpaper1.jpg", "theme": "hacker", "timestamp": "..."},
    {"path": "C:/path/to/wallpaper2.jpg", "theme": "nature", "timestamp": "..."},
    # ...
]
```

### 2. Sentiment Detection
```python
negative_keywords = [
    "valo lagche na", "pasondo hoyni", "change koro", 
    "onno wallpaper", "eta na", "bhalo na", "like na",
    "different wallpaper", "another wallpaper"
]

if any(keyword in user_text.lower() for keyword in negative_keywords):
    # Trigger alternative wallpaper flow
    handle_wallpaper_dislike()
```

### 3. Alternative Wallpaper Sources
```python
def get_alternative_wallpaper(theme, seed=None):
    """Get different wallpaper from same theme"""
    if seed is None:
        seed = random.randint(1, 10000)
    
    sources = [
        f"https://picsum.photos/seed/{theme}{seed}/1920/1080",
        f"https://source.unsplash.com/1920x1080/?{theme}",
        # More sources...
    ]
    
    return random.choice(sources)
```

### 4. Undo/Restore Function
```python
def restore_previous_wallpaper():
    """Restore the wallpaper before current one"""
    if len(wallpaper_history) >= 2:
        previous = wallpaper_history[-2]
        pc("theme_wallpaper", name=previous["path"])
        return f"Restored: {previous['theme']} wallpaper"
    else:
        return "No previous wallpaper in history"
```

---

## 📝 **OS_EXECUTOR Prompt Addition:**

```
- WALLPAPER FEEDBACK HANDLING (CRITICAL):
  * If user says wallpaper "valo lagche na", "pasondo hoyni", "change koro", "onno dao":
    OPTION A: Download DIFFERENT wallpaper from SAME theme (change seed/source)
    OPTION B: Ask user for preferred theme and download that
    OPTION C: Restore previous wallpaper from history (if available)
  * NEVER just say "okay" without taking action
  * ALWAYS offer alternatives or solutions
  * Examples:
    - User: "hacker wallpaper ta valo lagche na"
    - Maya: "Āchha, ami onno ekta hacker wallpaper download korchi..."
    - Action: Download different hacker wallpaper with new seed
```

---

## 🎯 **Conversation Examples:**

### Example 1: Same Theme, Different Image
```
User: "ekta hacker wallpaper lagiye dao"
Maya: *downloads & sets hacker wallpaper 1*
      "Hacker wallpaper set hoye gechhe!"

User: "eta valo lagche na"
Maya: "Āchha, ami onno ekta try korchi..."
      *downloads & sets hacker wallpaper 2*
      "Etake kemon lagche?"
```

### Example 2: Theme Change
```
User: "srikrishna er wallpaper lagao"
Maya: *downloads & sets Srikrishna wallpaper*

User: "eta pasondo hoyni, onno kichhu dao"
Maya: "Āchha! Ki dhoro wallpaper dekhte chao?
       Nature, minimal, dark theme, naki onno kichhu?"

User: "nature wallpaper dao"
Maya: *downloads & sets nature wallpaper*
      "Nature wallpaper set kore dilam!"
```

### Example 3: Restore Previous
```
User: "wallpaper change koro"
Maya: *changes wallpaper*

User: "na na, agerta better chilo"
Maya: "Āchha, ami purano wallpaper firiye dichhi..."
      *restores previous*
      "Purano wallpaper back!"
```

### Example 4: Manual Selection
```
User: "wallpaper ta bhalo na"
Maya: "Display Settings khulchhi, 
       tumi nijei choose koro wallpaper?"
      *opens Display Settings*
```

---

## 🔄 **Workflow Diagram:**

```
User: "wallpaper valo lagche na"
           ↓
    Detect negative feedback
           ↓
    ┌──────┴──────┐
    ↓             ↓
Same Theme?   New Theme?
    ↓             ↓
Download      Ask user
different     preference
image            ↓
    ↓         Download
Set it        new theme
    ↓             ↓
"Etake       "Etake
 kemon?"      kemon?"
```

---

## 💾 **Data Storage for History:**

### Option 1: In-Memory (Simple)
```python
# Global variable
WALLPAPER_HISTORY = []

def add_to_history(path, theme):
    WALLPAPER_HISTORY.append({
        "path": path,
        "theme": theme,
        "timestamp": time.time()
    })
    if len(WALLPAPER_HISTORY) > 5:
        WALLPAPER_HISTORY.pop(0)  # Keep only last 5
```

### Option 2: File-Based (Persistent)
```python
# Store in JSON file
HISTORY_FILE = "C:/Users/palni/.maya/wallpaper_history.json"

def save_history():
    with open(HISTORY_FILE, 'w') as f:
        json.dump(WALLPAPER_HISTORY, f)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return []
```

---

## ✅ **Implementation Checklist:**

- [ ] Add sentiment detection for negative feedback
- [ ] Implement alternative wallpaper download (different seeds)
- [ ] Add wallpaper history tracking (last 5)
- [ ] Add undo/restore previous wallpaper function
- [ ] Update OS_EXECUTOR prompt with feedback handling
- [ ] Test conversation flows
- [ ] Add theme suggestion logic

---

## 🎨 **Smart Features:**

### 1. Learn User Preferences
```python
# Track which wallpapers user kept vs changed
user_preferences = {
    "liked_themes": ["nature", "minimal"],
    "disliked_themes": ["dark", "abstract"],
    "average_change_time": 120  # seconds before changing
}
```

### 2. Proactive Suggestions
```python
if time_on_current_wallpaper < 60:  # Changed quickly = didn't like
    # Next time, avoid similar themes
    avoid_themes.append(current_theme)
```

---

## 🚀 **Final Behavior:**

**Maya will:**
1. ✅ Detect negative feedback ("valo lagche na")
2. ✅ Offer alternatives from same theme
3. ✅ Ask for different theme preferences
4. ✅ Maintain history for undo
5. ✅ Learn from user choices
6. ✅ NEVER just say "okay" without action

**Maya will NOT:**
- ❌ Ignore feedback
- ❌ Give up and ask user to do it manually
- ❌ Repeat same wallpaper again

---

**Status:** 📝 Design Complete — Ready for Implementation!
