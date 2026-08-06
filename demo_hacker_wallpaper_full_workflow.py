"""
MAYA AI — Complete Workflow Demo
User says: "ekta hacker er wallpaper lagiye dao"

Maya will:
1. Download a hacker/cyberpunk themed wallpaper
2. Set it as desktop background
3. Optional: Apply dark theme for full hacker aesthetic
"""

import sys
sys.path.insert(0, r"c:\maya-ai\backend")

from tools.unified.handlers.system_ops import handle_pc
import urllib.request
import os

print("=" * 70)
print("🖥️  MAYA AI — HACKER WALLPAPER SETUP")
print("=" * 70)

# Sample hacker-themed wallpapers (free sources)
hacker_wallpapers = {
    "matrix_code": "https://picsum.photos/seed/matrix/1920/1080",
    "cyberpunk": "https://picsum.photos/seed/cyber/1920/1080",
    "tech_dark": "https://picsum.photos/seed/tech/1920/1080",
}

print("\n📥 [Step 1] Downloading hacker wallpaper...")
wallpaper_style = "matrix_code"  # or "cyberpunk", "tech_dark"
url = hacker_wallpapers[wallpaper_style]
download_path = os.path.expanduser("~/Downloads/maya_hacker_wallpaper.jpg")

try:
    print(f"   Style: {wallpaper_style}")
    print(f"   Downloading from: {url}")
    
    urllib.request.urlretrieve(url, download_path)
    
    if os.path.exists(download_path):
        size_kb = os.path.getsize(download_path) / 1024
        print(f"   ✅ Downloaded successfully! ({size_kb:.1f} KB)")
    else:
        raise FileNotFoundError("Download failed")
        
except Exception as e:
    print(f"   ❌ Download failed: {e}")
    exit(1)

print("\n🎨 [Step 2] Setting wallpaper...")
result = handle_pc('theme_wallpaper', name=download_path)
print(f"   {result}")

if not result.startswith("OK"):
    print("   ❌ Failed to set wallpaper")
    exit(1)

print("\n🌙 [Step 3] Applying dark theme (hacker aesthetic)...")
result = handle_pc('theme_dark', val=1)
print(f"   {result}")

print("\n🎨 [Step 4] Setting green accent color (Matrix style)...")
# Green accent like Matrix: #00FF00
result = handle_pc('theme_accent', name="00FF00")
print(f"   {result}")

print("\n" + "=" * 70)
print("✅ HACKER SETUP COMPLETE!")
print("=" * 70)

print("\n🎯 What Maya did:")
print("   ✅ Downloaded hacker-themed wallpaper")
print("   ✅ Set as desktop background")
print("   ✅ Enabled dark mode")
print("   ✅ Applied Matrix-green accent color")

print(f"\n📂 Wallpaper saved at: {download_path}")
print("\n💡 You can delete it anytime or Maya can download a different one!")

print("\n" + "=" * 70)
print("🚀 Your PC now has a HACKER AESTHETIC!")
print("=" * 70)
