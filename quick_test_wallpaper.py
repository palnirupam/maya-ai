"""Quick Test: Set Hacker Wallpaper"""
import sys
sys.path.insert(0, r"c:\maya-ai\backend")
from tools.unified.handlers.system_ops import handle_pc
import urllib.request, os

print("🔄 Downloading hacker wallpaper...")
path = r"C:\Users\palni\Downloads\hacker_test.jpg"
urllib.request.urlretrieve("https://picsum.photos/seed/hacker/1920/1080", path)
print(f"✅ Downloaded: {path}")

print("\n🎨 Setting wallpaper...")
result = handle_pc('theme_wallpaper', name=path)
print(result)

print("\n🌙 Applying dark mode...")
result = handle_pc('theme_dark', val=1)
print(result)

print("\n✅ DONE! Check your desktop!")
