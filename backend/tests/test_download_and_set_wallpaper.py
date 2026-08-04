"""
Test: Download a hacker wallpaper from internet and set it
"""

import sys
sys.path.insert(0, r"c:\maya-ai\backend")

from tools.unified.handlers.system_ops import handle_pc
import urllib.request
import os

print("=" * 60)
print("MAYA AI — DOWNLOAD & SET HACKER WALLPAPER")
print("=" * 60)

# Sample hacker/cyberpunk wallpapers (royalty-free)
wallpaper_urls = [
    "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=1920&h=1080&fit=crop",  # Tech/coding
    "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=1920&h=1080&fit=crop",  # Matrix style
]

print("\n[1] Downloading hacker-themed wallpaper...")
download_path = os.path.expanduser("~/Pictures/maya_hacker_wallpaper.jpg")

try:
    # Download first available wallpaper
    url = wallpaper_urls[0]
    print(f"   URL: {url}")
    print(f"   Saving to: {download_path}")
    
    urllib.request.urlretrieve(url, download_path)
    print("   ✅ Download successful!")
    
    # Verify file exists
    if os.path.exists(download_path):
        file_size = os.path.getsize(download_path) / 1024  # KB
        print(f"   📁 File size: {file_size:.1f} KB")
    
    print("\n[2] Setting wallpaper...")
    result = handle_pc('theme_wallpaper', name=download_path)
    print(f"   Result: {result}")
    
    if result.startswith("OK"):
        print("\n" + "=" * 60)
        print("✅ HACKER WALLPAPER SET SUCCESSFULLY!")
        print("=" * 60)
        print(f"\n📍 Wallpaper location: {download_path}")
    else:
        print("\n❌ Failed to set wallpaper")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nNote: Internet connection required for download.")

print("\n💡 Maya can:")
print("   1. Search for wallpapers online")
print("   2. Download them")
print("   3. Set as desktop background")
print("   4. All in one command!")
