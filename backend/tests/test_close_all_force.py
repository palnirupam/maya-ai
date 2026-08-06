"""
Test close_apps_except with force close functionality.

Problem: "Close all" was leaving some apps open because they didn't respond
to gentle window.close() method.

Solution: Added taskkill fallback for stubborn windows, similar to close_app().
"""

print("Testing close_apps_except import...")
from backend.tools.desktop.apps import close_apps_except

print("✅ Import successful!")
print("\nFunction signature:")
print(close_apps_except.__doc__)

print("\n" + "="*60)
print("MANUAL TEST INSTRUCTIONS:")
print("="*60)
print("\n1. Open several apps (Chrome, Notepad, Calculator, etc.)")
print("2. Run Maya and say: 'Close all apps'")
print("3. Check that ALL apps close (except Maya)")
print("\nExpected behavior:")
print("✅ Apps that respond to window.close() → Close normally")
print("✅ Stubborn apps → Force-killed with taskkill")
print("✅ Maya/runtime windows → Protected (stay open)")
print("\nResult message should show:")
print("- Total closed count")
print("- (X force-killed) if any apps needed force close")
print("- List of closed app names")

print("\n" + "="*60)
print("CODE CHANGES:")
print("="*60)
print("\n1. Phase 1: Try gentle window.close() (existing)")
print("2. Phase 2: Detect stubborn windows (enhanced)")
print("3. Phase 3: Force-kill with taskkill (NEW)")
print("\nKey improvements:")
print("- Uses win32gui.FindWindow() to get window HWND")
print("- Uses win32process.GetWindowThreadProcessId() to get PID")
print("- Runs taskkill /F /T /PID <pid> for stubborn windows")
print("- Verifies each kill with _wait_for_process_exit()")
print("- Skips system/protected processes")
print("- Reports (X force-killed) in success message")

print("\n✅ Test file created. Ready for manual testing!")
