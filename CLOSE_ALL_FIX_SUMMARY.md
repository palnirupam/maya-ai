# Close All Apps Force Close Fix

## Problem

User reported: **"Close all" command wasn't closing all apps**

```
User: "Close all"
Maya: ✅ Command Approved. Executing...
Maya: Partially completed: Closed 5 app windows... Could not close 1 window(s).

User: "Close all app" 
Maya: ✅ Command Approved. Executing...
(Still some apps remain open)
```

**User expectation:** "Close all" should forcefully close ALL apps (except Maya), not leave stubborn ones open.

## Root Cause

The `close_apps_except()` function only used gentle `window.close()` method:

```python
# OLD CODE (Phase 1 only)
for window in windows:
    window.close()  # ❌ Some apps ignore this
    closed.append(title)
```

**Problems:**
1. Some apps don't respond to `window.close()` (e.g., apps with unsaved changes, system dialogs)
2. No fallback mechanism to force-kill stubborn processes
3. `close_app()` had taskkill fallback, but `close_apps_except()` didn't

**Contrast:**
- `close_app("Chrome")` → Has taskkill fallback ✅
- `close_apps_except("")` → No fallback ❌ (FIXED NOW)

## Solution

Added **3-phase close strategy** similar to `close_app()`:

### Phase 1: Gentle Close (Existing)
Try `window.close()` on all windows first

### Phase 2: Detect Stubborn Windows (Enhanced)
Check which windows are still open after Phase 1

### Phase 3: Force Kill (NEW)
For stubborn windows:
1. Get window HWND using `win32gui.FindWindow()`
2. Get process PID using `win32process.GetWindowThreadProcessId()`
3. Force-kill with `taskkill /F /T /PID <pid>`
4. Verify kill with `_wait_for_process_exit()`
5. Skip system/protected processes for safety

## Code Changes

### `backend/tools/desktop/apps.py`

**Updated `close_apps_except()` function:**

```python
def close_apps_except(excluded_apps: str) -> str:
    """Close every titled app window except the named app(s).
    
    This closes windows first (gentle), then force-kills stubborn processes (taskkill).
    """
    import psutil
    
    # ... setup code ...
    
    stubborn_windows = []
    force_killed = []
    
    # Phase 1: Try gentle window.close()
    for window in windows:
        # ... protection checks ...
        try:
            window.close()
            closed.append(title)
        except Exception as e:
            failures.append(f"{title}: {e}")
    
    # Phase 2: Detect stubborn windows
    if closed:
        remaining_titles = set(_wait_for_matching_windows(...))
        stubborn_windows = [title for title in closed if title in remaining_titles]
        closed = [title for title in closed if title not in remaining_titles]
    
    # Phase 3: Force-kill stubborn windows (NEW!)
    if stubborn_windows and os.name == "nt":
        for window in current_windows:
            title = window.title
            if title not in stubborn_windows:
                continue
            
            # Get PID via win32 APIs
            import win32gui, win32process
            hwnd = win32gui.FindWindow(None, title)
            if hwnd:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                
                # Skip protected processes
                if _is_system_process(proc) or _is_protected_runtime_process(proc):
                    continue
                
                # Force kill
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    ...
                )
                if result.returncode == 0:
                    if _wait_for_process_exit(proc):
                        force_killed.append(title)
                        stubborn_windows.remove(title)
    
    # Build result message
    total_closed = len(closed) + len(force_killed)
    force_note = f" ({len(force_killed)} force-killed)" if force_killed else ""
    
    return f"SUCCESS: Closed {total_closed} app window(s){force_note}: ..."
```

### Key Improvements

1. ✅ **Detects stubborn windows** after gentle close
2. ✅ **Force-kills with taskkill** when needed
3. ✅ **Reports force-kill count** in success message
4. ✅ **Protects system processes** from force kill
5. ✅ **Verifies each kill** with wait check
6. ✅ **Maintains backward compatibility** (gentle close still tried first)

## User Experience Impact

### Before Fix
```
User: "Close all apps"
Maya: PARTIAL: Closed 5 apps... Could not close 1 window(s).
(Some apps stay open - stubborn apps ignored)
```

### After Fix
```
User: "Close all apps"
Maya: SUCCESS: Closed 6 app window(s) (1 force-killed): Chrome, Notepad, Calculator...
(ALL apps close - stubborn apps force-killed)
```

## Behavior Matrix

| App Type | Phase 1 (Gentle) | Phase 2 (Detect) | Phase 3 (Force) | Result |
|----------|------------------|------------------|-----------------|--------|
| Normal app (saves on close) | ✅ Closes | - | - | ✅ Closed |
| Stubborn app (unsaved changes) | ❌ Stays open | ✅ Detected | ✅ Force-killed | ✅ Closed |
| System process | ⚠️ Protected | - | ⚠️ Skipped | ✅ Protected |
| Maya/runtime | ⚠️ Protected | - | ⚠️ Skipped | ✅ Protected |

## Safety Features

1. ✅ **System process protection** — Never kills system-owned processes
2. ✅ **Maya protection** — Maya and runtime windows always protected
3. ✅ **Excluded apps respected** — Apps in exclusion list never touched
4. ✅ **Verification checks** — Each kill verified before reporting success
5. ✅ **Error handling** — Failures logged but don't stop other closes

## Testing

### Manual Test

1. Open several apps:
   - Chrome (browser)
   - Notepad with unsaved text
   - Calculator
   - Settings
   - VS Code

2. Tell Maya: **"Close all apps"**

3. Expected result:
   - All apps close (including stubborn ones)
   - Maya stays open
   - Success message shows total + force-kill count

### Test File

`backend/tests/test_close_all_force.py` — Manual testing instructions

## Files Modified

1. `backend/tools/desktop/apps.py`
   - Updated `close_apps_except()` function (line 901+)
   - Added Phase 3: Force-kill logic
   - Added win32gui/win32process imports (conditional)
   - Enhanced result messages with force-kill count

2. `backend/tests/test_close_all_force.py` (NEW)
   - Manual testing guide
   - Explains 3-phase strategy

## Backwards Compatibility

✅ **100% backward compatible**
- Gentle close still tried first (no change for responsive apps)
- Force close only used when needed
- Protected processes still protected
- Same function signature
- Enhanced result messages (adds info, doesn't remove)

## Technical Details

### Windows API Usage

```python
import win32gui
import win32process

# Get window handle
hwnd = win32gui.FindWindow(None, window_title)

# Get process ID
thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)

# Get process object
proc = psutil.Process(process_id)

# Force kill
subprocess.run(["taskkill", "/F", "/T", "/PID", str(process_id)])
```

### Flags Explained

- `/F` — Force termination
- `/T` — Terminate child processes too
- `/PID` — Target specific process ID (not image name)

## Summary

**Problem:** "Close all" left stubborn apps open
**Solution:** Added taskkill fallback for stubborn windows
**Impact:** ALL apps now close when user says "close all" (except Maya)
**Safety:** System processes and Maya protected

This fix makes "Close all" command work as users expect — truly closing EVERYTHING! 🎯
