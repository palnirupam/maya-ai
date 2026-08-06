---
name: file-organizer
description: Intelligent file organization, cleanup, duplicate detection, and smart sorting
emoji: 📁
priority: 4
---

## Instructions

When user needs file organization, or says:
- "Organize my files"
- "Clean up this folder"
- "My downloads are messy"
- "Find duplicate files"
- "Sort files"

Activate **File Organizer Mode**:

### Quick Organize

```
📁 FILE ORGANIZER

Target folder: [folder path]

🔍 **ANALYZING...**

Found:
- 156 files
- 12 subfolders
- 2.3 GB total size
- Last organized: Never / 30 days ago

**ISSUES DETECTED:**
⚠️ 45 files in root (should be in folders)
⚠️ 12 duplicate files (1.2 GB wasted)
⚠️ 23 old files (>1 year)
⚠️ 8 large files (>100 MB each)
❌ 5 incomplete downloads (.crdownload, .tmp)

**ORGANIZE OPTIONS:**

1. **🎯 Smart Auto-Organize**
   - Sort by type (Documents, Images, Videos, etc.)
   - Create dated folders
   - Move everything organized

2. **🎨 Custom Organization**
   - You choose folder structure
   - I'll move files accordingly

3. **🧹 Deep Clean**
   - Remove duplicates
   - Delete temp files
   - Archive old files

Which option? (or do all 3)
```

### Auto-Organization Rules

```
file("organize", path="C:/Users/Downloads")
```

This automatically:

**By File Type:**
```
📁 Downloads/
├── 📄 Documents/
│   ├── PDFs/
│   ├── Word/
│   ├── Excel/
│   └── Text/
├── 🖼️ Images/
│   ├── Screenshots/
│   ├── Photos/
│   └── Graphics/
├── 🎵 Media/
│   ├── Music/
│   ├── Videos/
│   └── Audio/
├── 📦 Archives/
│   ├── ZIP/
│   └── RAR/
├── 💿 Installers/
│   └── Setup files/
└── 🗂️ Others/
```

**By Date (optional):**
```
📁 Documents/
├── 2026/
│   ├── 2026-08-August/
│   ├── 2026-07-July/
│   └── 2026-06-June/
└── 2025/
```

**By Project (advanced):**
```
Detects project patterns:
- Files with similar names
- Files from same date range
- Related file types
→ Groups them automatically
```

### Duplicate File Finder

```
🔍 DUPLICATE DETECTOR

Scanning: [folder]

**DUPLICATES FOUND:**

**Set 1:** vacation.jpg
- C:/Pictures/vacation.jpg (2.5 MB) ⭐ Original
- C:/Desktop/vacation.jpg (2.5 MB) 📄 Copy
- C:/Downloads/vacation (1).jpg (2.5 MB) 📄 Copy

Action: Keep original, delete 2 copies
Space saved: 5 MB

**Set 2:** report.pdf
- C:/Documents/report.pdf (1.2 MB, modified 2026-08-01) ⭐ Latest
- C:/Desktop/report.pdf (1.1 MB, modified 2026-07-28) 📄 Older
- C:/Downloads/report.pdf (1.1 MB, modified 2026-07-28) 📄 Older

Action: Keep latest, delete 2 older versions
Space saved: 2.2 MB

**Set 3-8:** [More duplicates]

**SUMMARY:**
- 8 duplicate sets found
- 16 files can be deleted
- 45 MB can be recovered

Delete all duplicates? (I'll move to Recycle Bin, not permanent delete)
```

### Smart Cleanup

```
🧹 SMART CLEANUP

Folder: [path]

**SAFE TO DELETE:**

**1. Temporary Files (23 files, 156 MB)**
- .tmp files
- .cache files
- Browser temp files
Action: ✅ Delete (recoverable from Recycle Bin)

**2. Old Downloads (15 files, 890 MB)**
- Downloaded >6 months ago
- Not opened since download
- Likely not needed anymore
List:
  - old_installer_v1.exe (120 MB, 8 months old)
  - random_doc.pdf (5 MB, 1 year old)
  [...]
Action: 🗄️ Archive or Delete?

**3. Incomplete Downloads (8 files, 50 MB)**
- .crdownload
- .part
- .tmp
Action: ✅ Delete (these are broken)

**4. Empty Folders (12 folders)**
Action: ✅ Delete

**5. System Junk**
- Windows.old (if exists)
- Temp folders
- Recycle Bin

**POTENTIAL SPACE RECOVERY: 1.1 GB**

Proceed with cleanup?
```

### File Naming Convention

```
📝 FILE RENAMING

Found files with poor names:
- Untitled.docx
- IMG_1234.jpg
- New Document (1).pdf
- asjdklasjd.txt

**SMART RENAME:**

Using AI to detect content:
❌ IMG_1234.jpg → ✅ family_beach_vacation_2026.jpg
❌ Untitled.docx → ✅ project_proposal_maya_ai.docx
❌ New Document (1).pdf → ✅ meeting_notes_2026_08_04.pdf

**BATCH RENAME PATTERNS:**

Pattern: [Project]_[Type]_[Date]
Examples:
- MayaAI_Design_2026-08-01.psd
- MayaAI_Code_2026-08-02.py
- MayaAI_Docs_2026-08-03.md

Apply naming convention to [folder]?
```

### Archive Old Files

```
🗄️ FILE ARCHIVAL

**Files not accessed in 6+ months:**

Total: 45 files (2.3 GB)

**Archive Strategy:**

1. **Create Archive:**
   - Archive_2025_H2.zip
   - Contains: All files from Jul-Dec 2025
   - Size: ~800 MB (compressed)

2. **Store Archive:**
   - Location: D:/Archives/
   - Or: Cloud storage (Google Drive/Dropbox)
   - Or: External hard drive

3. **Remove Originals:**
   - Archived files moved to Recycle Bin
   - Space freed: 1.5 GB
   - Can restore anytime from archive

Proceed with archival?
```

### Smart Search & Sort

```
🔎 SMART FILE SEARCH

**Find files by:**

1. **Type:** "Show me all PDFs"
2. **Date:** "Files from last week"
3. **Size:** "Files larger than 100 MB"
4. **Content:** "Files containing 'Maya AI'"
5. **Pattern:** "All screenshots"

Example:
Query: "Large video files from this month"

Results:
1. tutorial_recording.mp4 (850 MB, Aug 1)
2. project_demo.mov (650 MB, Aug 3)
3. meeting_recording.mp4 (420 MB, Aug 4)

Actions available:
- Move to specific folder
- Delete
- Compress
- Upload to cloud
```

### Folder Structure Suggestions

```
💡 RECOMMENDED FOLDER STRUCTURE

Based on your files, I suggest:

**For Work:**
```
📁 Work/
├── 📊 Projects/
│   ├── ProjectA/
│   ├── ProjectB/
│   └── ProjectC/
├── 📄 Documents/
│   ├── Reports/
│   ├── Presentations/
│   └── Spreadsheets/
├── 🗓️ Meetings/
│   └── [Dated folders]/
└── 📚 Resources/
    ├── Templates/
    └── References/
```

**For Personal:**
```
📁 Personal/
├── 💰 Finance/
│   ├── Taxes/
│   ├── Bills/
│   └── Receipts/
├── 🏥 Health/
├── 🎓 Learning/
│   └── Courses/
└── 🎨 Creative/
    ├── Photos/
    ├── Videos/
    └── Designs/
```

Create this structure?
```

### File Recovery Assistant

```
🔄 FILE RECOVERY

Lost a file? Let me help:

**1. Recent Files:**
Showing 20 most recently modified:
- report.docx (modified 2 min ago)
- project.py (modified 15 min ago)
[...]

**2. Search Recycle Bin:**
Found 45 deleted files from last 7 days:
- important.pdf (deleted today)
- old_code.py (deleted yesterday)
[...]

**3. Search All Drives:**
Searching for: [filename]
Found 3 matches:
- C:/Users/Documents/file.pdf
- D:/Backup/file.pdf
- E:/OldFiles/file.pdf

**4. Check Backup Locations:**
- OneDrive sync folder
- Google Drive sync folder
- File History (if enabled)

Found your file? Which one to restore?
```

### Maintenance Schedule

```
🗓️ FILE MAINTENANCE SCHEDULE

**Daily (Automatic):**
- Sort new downloads by type
- Move screenshots to folder
- Clean temp files

**Weekly (Every Monday):**
- Duplicate file scan
- Empty Recycle Bin
- Archive old files

**Monthly (1st of month):**
- Deep clean all folders
- Review large files
- Organize photos by date
- Backup important folders

**Quarterly:**
- Review folder structure
- Archive old projects
- Free up space analysis

Next scheduled cleanup: Tomorrow 9 AM

Want to customize schedule?
```

### Space Analyzer

```
💾 DISK SPACE ANALYSIS

Drive C: [████████░░] 450 GB / 500 GB (90% full)

**Top Space Users:**

1. 📹 Videos (180 GB) - 36%
   Location: C:/Users/Videos/
   
2. 💿 Programs (95 GB) - 19%
   Location: C:/Program Files/
   
3. 🎮 Games (75 GB) - 15%
   Location: C:/Games/
   
4. 📷 Photos (60 GB) - 12%
   Location: C:/Users/Pictures/
   
5. 📄 Documents (25 GB) - 5%
   Location: C:/Users/Documents/

**RECOMMENDATIONS:**

1. Move videos to external drive (save 180 GB)
2. Uninstall unused programs (save ~20 GB)
3. Archive old photos (save ~30 GB)
4. Clean system files (save ~10 GB)

**Potential Space Recovery: 240 GB**

Which action first?
```

### Quick Actions

```
⚡ QUICK FILE ACTIONS

**Instant Commands:**

1. "Sort downloads" → Auto-organize Downloads folder
2. "Find big files" → Show files >100 MB
3. "Delete temp files" → Clean all temp
4. "Find duplicates in [folder]" → Duplicate scan
5. "Rename screenshots" → Batch rename with date
6. "Zip [folder]" → Compress folder
7. "Move [file] to [location]" → Smart move
8. "Show recent files" → Last 20 modified
9. "Empty recycle bin" → Permanent delete
10. "Backup [folder]" → Create backup copy

Just say the command!
```

### Best Practices Tips

```
💡 FILE ORGANIZATION BEST PRACTICES

**1. Naming Files:**
✅ DO: descriptive_name_2026_08_04.pdf
❌ DON'T: Untitled (1).pdf

**2. Folder Depth:**
✅ DO: Max 3-4 levels deep
❌ DON'T: A/B/C/D/E/F/G/file.pdf

**3. Regular Cleanup:**
✅ DO: Weekly cleanup routine
❌ DON'T: Clean once per year

**4. Backup Rule (3-2-1):**
- 3 copies of data
- 2 different storage types
- 1 off-site backup

**5. Downloads Folder:**
✅ DO: Organize immediately
❌ DON'T: Let it accumulate

Want me to enforce these rules automatically?
```
