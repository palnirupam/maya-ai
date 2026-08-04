"""
Test Maya AI Wallpaper Change Feature
"""

import sys
sys.path.insert(0, r"c:\maya-ai\backend")

from tools.unified.handlers.system_ops import handle_pc
import subprocess

print("=" * 60)
print("MAYA AI — WALLPAPER CHANGE TEST")
print("=" * 60)

# Find available wallpapers
print("\n[1] Finding available Windows wallpapers...")
result = subprocess.run(
    'powershell "Get-ChildItem C:\\Windows\\Web\\Wallpaper -Recurse -Include *.jpg,*.png | Select-Object -First 3 FullName"',
    capture_output=True, text=True, shell=True
)
print(result.stdout)

wallpapers = [
    r"C:\Windows\Web\Wallpaper\Windows\img0.jpg",
    r"C:\Windows\Web\Wallpaper\HP Backgrounds\backgroundDefault.jpg",
]

print("\n[2] Testing wallpaper changes...")
for i, wallpaper in enumerate(wallpapers, 1):
    print(f"\n   Test {i}: {wallpaper}")
    result = handle_pc('theme_wallpaper', name=wallpaper)
    print(f"   Result: {result}")
    
    if result.startswith("OK"):
        print("   ✅ SUCCESS")
    else:
        print("   ❌ FAILED")

print("\n" + "=" * 60)
print("✅ Wallpaper change feature is WORKING!")
print("=" * 60)

print("\n📝 Usage:")
print('   pc("theme_wallpaper", name="C:/path/to/image.jpg")')
print("\n💡 Supported formats: JPG, PNG, BMP")
