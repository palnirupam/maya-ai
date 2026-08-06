# 📂 Maya AI — Wallpaper Storage Location

## 🎯 **Where are downloaded wallpapers stored?**

### 📍 **Default Storage Location:**
```
C:\Users\palni\Downloads\
```

---

## 📁 **Current Stored Wallpapers:**

| Filename | Size | Location |
|----------|------|----------|
| `maya_hacker_wallpaper.jpg` | 193.7 KB | Downloads folder |
| `maya_hacker_wallpaper_test.jpg` | 334.9 KB | Downloads folder |
| `hacker_test.jpg` | (if exists) | Downloads folder |

**Full Paths:**
```
C:\Users\palni\Downloads\maya_hacker_wallpaper.jpg
C:\Users\palni\Downloads\maya_hacker_wallpaper_test.jpg
```

---

## 🔧 **How Maya Handles Wallpaper Storage:**

### Current Behavior:
```python
# Maya downloads to Downloads folder
download_path = "C:/Users/palni/Downloads/maya_<theme>_wallpaper.jpg"

# Examples:
maya_hacker_wallpaper.jpg      # For "hacker wallpaper"
maya_srikrishna_wallpaper.jpg  # For "srikrishna wallpaper"
maya_nature_wallpaper.jpg      # For "nature wallpaper"
```

### Naming Convention:
```
maya_<theme_name>_wallpaper.jpg
```

---

## 💡 **Storage Options:**

### Option 1: Keep in Downloads (Current) ✅
**Pros:**
- Easy to find
- User can manually manage
- Standard location

**Cons:**
- Downloads folder can get messy
- May get deleted accidentally

---

### Option 2: Create Dedicated Folder (Recommended) 🎨
**Location:** `C:\Users\palni\Pictures\Maya Wallpapers\`

**Pros:**
- Organized
- Separated from other downloads
- Easy to browse all Maya wallpapers

**Cons:**
- Needs folder creation logic

---

## 🛠️ **Implementation:**

### Current Code:
```python
# In test scripts
download_path = os.path.expanduser("~/Downloads/maya_hacker_wallpaper.jpg")
```

### Recommended Code:
```python
# Create dedicated wallpaper folder
wallpaper_folder = os.path.expanduser("~/Pictures/Maya Wallpapers")
os.makedirs(wallpaper_folder, exist_ok=True)

# Save wallpapers there
download_path = os.path.join(wallpaper_folder, f"maya_{theme}_wallpaper.jpg")
```

---

## 📋 **User Options:**

### To View Downloaded Wallpapers:
```bash
# Open Downloads folder
explorer C:\Users\palni\Downloads

# Or using Maya
"Downloads folder kholo"
```

### To Delete Old Wallpapers:
```bash
# Manual cleanup
del C:\Users\palni\Downloads\maya_*_wallpaper.jpg

# Or using Maya
"purano wallpaper gulo delete kore dao"
```

---

## 🎯 **Recommended Changes:**

### 1. Create Dedicated Wallpaper Folder
```python
# In system_ops.py or wallpaper handler
WALLPAPER_FOLDER = os.path.expanduser("~/Pictures/Maya Wallpapers")
os.makedirs(WALLPAPER_FOLDER, exist_ok=True)
```

### 2. Add Cleanup Option
```python
# Delete wallpapers older than 7 days
def cleanup_old_wallpapers():
    cutoff = time.time() - (7 * 24 * 60 * 60)
    for file in os.listdir(WALLPAPER_FOLDER):
        if file.startswith("maya_") and file.endswith(".jpg"):
            path = os.path.join(WALLPAPER_FOLDER, file)
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
```

### 3. Add User Configuration
```python
# Let user choose storage location
pc("wallpaper_storage", name="C:/Custom/Path")
```

---

## 📊 **Current Status:**

| Aspect | Status | Notes |
|--------|--------|-------|
| Storage Location | ✅ Working | Downloads folder |
| File Naming | ✅ Clear | `maya_<theme>_wallpaper.jpg` |
| Organization | ⚠️ Basic | All in Downloads |
| Cleanup | ❌ Manual | User must delete manually |

---

## 🚀 **Quick Access Commands:**

### View Wallpapers:
```bash
# Windows Explorer
explorer C:\Users\palni\Downloads

# PowerShell
ls C:\Users\palni\Downloads\*wallpaper*
```

### Delete Specific Wallpaper:
```bash
del "C:\Users\palni\Downloads\maya_hacker_wallpaper.jpg"
```

### View Wallpaper Details:
```bash
Get-Item "C:\Users\palni\Downloads\maya_hacker_wallpaper.jpg" | Select Name, Length, LastWriteTime
```

---

## 💡 **User-Friendly Summary:**

**তোমার downloaded wallpapers আছে:**
```
📂 C:\Users\palni\Downloads\
   ├── maya_hacker_wallpaper.jpg (193.7 KB)
   └── maya_hacker_wallpaper_test.jpg (334.9 KB)
```

**এগুলো দেখতে চাইলে:**
- Downloads folder খোলো
- অথবা Maya-কে বলো: "Downloads folder kholo"

**Delete করতে চাইলে:**
- Manual: Right-click → Delete
- অথবা Maya-কে বলো: "maya wallpaper gulo delete koro"

---

**Conclusion:** Wallpapers currently store হয় **Downloads folder-এ**, but একটা dedicated **"Maya Wallpapers"** folder create করা আরও organized হবে! 🎨
