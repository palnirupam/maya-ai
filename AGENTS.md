# Maya AI — Tool Usage Guide

## Core Tools (low token, high power)

Use these 2 router tools instead of individual function tools:

### file(action, src, dst, name, n, path)
All file operations in one tool:
- `file("copy", src="C:/a.txt", dst="D:/b/")` — copy cross-drive
- `file("move", src="C:/a.txt", dst="D:/b/")` — move cross-drive
- `file("rename", src="C:/a.txt", dst="newname.txt")`
- `file("delete", src="C:/a.txt")`
- `file("read", src="C:/a.txt")`
- `file("write", src="C:/a.txt", dst="content here")`
- `file("ls", path="C:/folder")`
- `file("mkdir", path="C:/newfolder")`
- `file("search", name="report.pdf", n=5)` — finds across all drives
- `file("delete_by_name", name="report.pdf", n=5)` — find+delete
- `file("organize", path="C:/Downloads")` — auto-sort by type

**NEW: Compression (zero API cost)**
- `file("compress", src="C:/folder", dst="archive.zip")` — create ZIP/TAR archive
- `file("extract", src="archive.zip", dst="C:/output")` — extract archive
- `file("list_archive", src="archive.zip")` — list contents without extracting
- `file("compress_files", name="file1.txt,file2.doc", dst="files.zip")` — compress specific files

### pc(action, val, name, state, cmd)
All system control in one tool:
- `pc("volume", val=70)`
- `pc("brightness", val=50)`
- `pc("lock")` / `pc("mute")` / `pc("screenshot")`
- `pc("sleep")` / `pc("shutdown")` / `pc("restart")` / `pc("hibernate")`
- `pc("clipboard_read")` / `pc("clipboard_write", name="text")`
- `pc("process_list")` / `pc("process_kill", name="notepad")`
- `pc("battery")` / `pc("network")` / `pc("stats")`
- `pc("wifi_scan")` / `pc("wifi_connect", ssid="MyWiFi", password="pass")`
- `pc("wifi_disconnect")` / `pc("wifi_status")` / `pc("wifi_toggle", state="off")`
- `pc("bt_status")` / `pc("bt_toggle", state="on")` / `pc("bt_list")` / `pc("bt_remove", name="Speaker")`

**NEW: Multiple Monitor Configuration**
- `pc("display_list")` — List all connected displays
- `pc("display_settings")` — Open Display Settings
- `pc("display_orientation", val=0)` — Rotate display (0=landscape, 1=portrait, 2/3=flipped)
- `pc("display_extend", name="extend")` — Set mode: 'pc_only', 'duplicate', 'extend', 'second_only'

**NEW: Keyboard Shortcut Customization**
- `pc("hotkey_remap", name="CapsLock", state="Ctrl")` — Remap keys (uses AutoHotkey)
- `pc("hotkey_list")` — List all custom remappings
- `pc("hotkey_reset")` — Clear all remappings

**NEW: System Theme/Appearance**
- `pc("theme_dark", val=1)` — Dark mode ON (val=1) or Light mode (val=0)
- `pc("theme_accent", name="FF0000")` — Set accent color (hex)
- `pc("theme_wallpaper", name="C:/path/to/image.jpg")` — Change wallpaper
- `pc("theme_transparency", val=1)` — Enable/disable transparency effects

**NEW: Notification Center Interaction**
- `pc("notification_open")` — Open Notification Center
- `pc("notification_clear")` — Clear all notifications
- `pc("notification_list")` — List recent notifications
- `pc("notification_focus")` — Open Focus Assist (Do Not Disturb)

**NEW: Wallpaper Feedback & Management**
- `pc("wallpaper_dislike", name="hacker")` — User dislikes wallpaper, try different one from same theme
- `pc("wallpaper_restore")` — Restore previous wallpaper (undo)
- `pc("wallpaper_suggest", name="hacker")` — Get alternative theme suggestions
- `pc("wallpaper_like")` — Mark current wallpaper as liked (learn preferences)

**NEW: Browser Automation (zero API cost - keyboard shortcuts)**
- `pc("browser_tab_new")` — Open new browser tab
- `pc("browser_tab_close")` — Close current tab
- `pc("browser_tab_next")` — Switch to next tab
- `pc("browser_tab_prev")` — Switch to previous tab
- `pc("browser_tab_reopen")` — Reopen last closed tab
- `pc("browser_tab_switch", val=3)` — Switch to tab number 3
- `pc("browser_bookmark")` — Bookmark current page
- `pc("browser_bookmarks")` — Open bookmarks manager
- `pc("browser_history")` — Open browser history
- `pc("browser_downloads")` — Open downloads page
- `pc("browser_find")` — Find in page (Ctrl+F)
- `pc("browser_refresh")` — Refresh current page
- `pc("browser_back")` — Navigate back
- `pc("browser_forward")` — Navigate forward
- `pc("browser_open_url", name="https://google.com")` — Open URL in default browser
- `pc("browser_search", name="weather today")` — Search in new tab
- `pc("browser_fullscreen")` — Toggle fullscreen mode
- `pc("browser_zoom_in")` — Zoom in
- `pc("browser_zoom_out")` — Zoom out
- `pc("browser_zoom_reset")` — Reset zoom to 100%
- `pc("browser_incognito")` — Open incognito/private window
- `pc("browser_devtools")` — Open developer tools (F12)

**Usage Example:**
```python
# User: "wallpaper ta valo lagche na"
pc("wallpaper_dislike", name="hacker")  # Downloads & sets different hacker wallpaper

# User: "agerta better chilo"  
pc("wallpaper_restore")  # Restores previous wallpaper

# User: "onno theme suggest koro"
pc("wallpaper_suggest", name="hacker")  # Returns: "cyberpunk, tech, coding, matrix"

# User: "browser e notun tab kholo"
pc("browser_tab_new")  # Opens new tab

# User: "Downloads folder compress koro"
file("compress", src="C:/Users/Downloads", dst="downloads_backup.zip")

# User: "ei zip file er moddhe ki ache?"
file("list_archive", src="downloads_backup.zip")
```

## Legacy Tools (still available)
Individual tools (create_file, read_file, move_file, wifi_scan, etc.) still work for backward compatibility.

## Best Practices
1. Prefer `file()` and `pc()` — same power, fewer tokens
2. File paths: use forward slashes or raw strings
3. Cross-drive moves: just pass source + destination, auto-handled
4. Safety: system dirs + Maya project dir are automatically protected
