import os
import shutil
import glob
import datetime

def create_file(filepath: str, content: str) -> str:
    """
    Creates a new file at the specified path with the given content.
    If the parent directory does not exist, it will be created.
    """
    try:
        if not filepath or not filepath.strip():
            return "ERROR: File path cannot be empty."
        abs_path = os.path.abspath(filepath)
        dir_name = os.path.dirname(abs_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"SUCCESS: File created at {abs_path}"
    except Exception as e:
        return f"ERROR: Failed to create file {filepath}. {e}"

def read_file(filepath: str) -> str:
    """
    Reads the content of a file at the specified absolute path.
    """
    try:
        if not os.path.exists(filepath):
            return f"ERROR: File {filepath} does not exist."
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"ERROR: Failed to read file {filepath}. {e}"

def list_directory(directory_path: str) -> str:
    """
    Lists the contents of the specified directory.
    """
    try:
        if not os.path.exists(directory_path):
            return f"ERROR: Directory {directory_path} does not exist."
        
        items = os.listdir(directory_path)
        return f"Contents of {directory_path}:\n" + "\n".join(items)
    except Exception as e:
        return f"ERROR: Failed to list directory {directory_path}. {e}"

def delete_file(filepath: str) -> str:
    """
    Deletes the file at the specified absolute path. Use with extreme caution.
    """
    try:
        if not os.path.exists(filepath):
            return f"ERROR: File {filepath} does not exist."
        os.remove(filepath)
        return f"SUCCESS: Deleted {filepath}"
    except Exception as e:
        return f"ERROR: Failed to delete {filepath}. {e}"


def move_file(src: str, dst: str) -> str:
    """Move file or folder (cross-drive safe, auto-dedupe, parents created)."""
    if not os.path.exists(src):
        return f"ERR: missing {src}"
    dest = os.path.join(dst, os.path.basename(src)) if os.path.isdir(dst) else dst
    dest = _dedupe_path(dest)
    parent = os.path.dirname(dest)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    try:
        return f"OK: {shutil.move(src, dest)}"
    except Exception as e:
        return f"ERR: {src}->{dst} | {e}"


def move_items(items: list, dst_dir: str) -> str:
    """Batch move many files/folders into dst_dir. Returns per-item results."""
    if not os.path.isdir(dst_dir):
        os.makedirs(dst_dir, exist_ok=True)
    results = []
    for src in items:
        results.append(move_file(src, dst_dir))
    return "\n".join(results)


def search_local_files(query: str, root_path: str = None) -> str:
    """
    Recursively searches for files matching a query string in their name on the PC.
    Highly optimized: automatically skips heavy system folders (like AppData, node_modules, .git) for speed.
    Args:
        query (str): The filename or part of the name to search for (e.g. "report", "syllabus.pdf").
        root_path (str, optional): The directory path to search under. Defaults to the User's Home Profile directory (C:\\Users\\username).
    """
    import os
    if not root_path:
        root_path = os.path.expanduser("~") # Defaults to C:\Users\username
        
    if not os.path.exists(root_path):
        return f"ERROR: Search directory '{root_path}' does not exist."
        
    query_lower = query.lower().strip()
    matches = []
    max_results = 25
    
    # Folders to completely skip for speed and security
    skip_dirs = {
        'appdata', 'node_modules', '.git', '.venv', 'env', 'venv', 
        'temp', 'tmp', 'cache', 'system32', 'windows', 'documents and settings'
    }
    
    try:
        for root, dirs, files in os.walk(root_path):
            # Modify dirs in-place to prune heavy and system directories
            dirs[:] = [d for d in dirs if d.lower() not in skip_dirs and not d.startswith('.')]
            
            for file in files:
                if query_lower in file.lower():
                    full_path = os.path.join(root, file)
                    matches.append(full_path)
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break
                
        if not matches:
            return f"No files found matching '{query}' under '{root_path}'."
            
        results_str = f"Found {len(matches)} files matching '{query}':\n"
        results_str += "\n".join(f"- {path}" for path in matches)
        return results_str
    except Exception as e:
        return f"ERROR: File search failed. {e}"


# ── Fast file organizer ──────────────────────────────────────────────────────
_NAMED_FOLDERS = {
    "downloads": "Downloads", "download": "Downloads",
    "desktop": "Desktop",
    "documents": "Documents", "docs": "Documents",
    "pictures": "Pictures", "photos": "Pictures",
    "music": "Music",
    "videos": "Videos", "video": "Videos",
}

_CATEGORY_MAP = {
    "Images":     {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic", ".tiff", ".ico"},
    "Documents":  {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".xls", ".xlsx", ".csv", ".ppt", ".pptx"},
    "Videos":     {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "Audio":      {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Archives":   {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Installers": {".exe", ".msi", ".apk", ".dmg"},
    "Code":       {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".html", ".css", ".json", ".xml", ".sh", ".ipynb"},
}


def _resolve_folder(folder: str) -> str:
    """Map a friendly name ('downloads') or a path to an absolute directory path."""
    key = (folder or "").strip().lower()
    if key in _NAMED_FOLDERS:
        return os.path.join(os.path.expanduser("~"), _NAMED_FOLDERS[key])
    return os.path.abspath(os.path.expanduser(folder))


def _category_for(ext: str) -> str:
    ext = ext.lower()
    for category, exts in _CATEGORY_MAP.items():
        if ext in exts:
            return category
    return "Others"


def _is_unsafe_target(path: str) -> bool:
    """Refuse drive roots and system directories so we never shuffle Windows/Program Files."""
    p = os.path.abspath(path).rstrip("\\/").lower()
    if len(p) <= 3:  # a drive root like "c:" / "c:\"
        return True
    unsafe_roots = [
        os.environ.get("SystemRoot", "C:\\Windows").lower(),
        "c:\\program files", "c:\\program files (x86)",
    ]
    return any(p.startswith(root) for root in unsafe_roots)


def _dedupe_path(dest: str) -> str:
    """Return a non-colliding destination path by appending ' (1)', ' (2)', ..."""
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def organize_folder(folder: str = "downloads", strategy: str = "type", dry_run: bool = False) -> str:
    """
    Quickly organizes the loose files in a folder into tidy subfolders. Pure
    filesystem work (no GUI), so it runs fast in the background.
    Args:
        folder (str): A folder path OR a friendly name — 'downloads', 'desktop',
                      'documents', 'pictures', 'music', 'videos'. Defaults to 'downloads'.
        strategy (str): 'type' groups by file kind (Images/Documents/Videos/Audio/
                        Archives/Installers/Code/Others); 'date' groups by the
                        year-month (YYYY-MM) the file was last modified. Default 'type'.
        dry_run (bool): If True, only reports what WOULD move — moves nothing.
    Note: subfolders, hidden files and shortcuts (.lnk) are left untouched.
    """
    from ...unified.core.policy import is_safe_path

    target = _resolve_folder(folder)
    if not os.path.isdir(target):
        return f"ERROR: Folder '{folder}' -> '{target}' does not exist."
    if _is_unsafe_target(target) or not is_safe_path(target):
        return f"ERROR: Refusing to organize a system/root folder ('{target}') for safety."
    if os.path.islink(target) or (hasattr(os.path, "isjunction") and os.path.isjunction(target)):
        return f"ERROR: Refusing to organize a symlink/reparse-point folder ('{target}')."

    strategy = (strategy or "type").strip().lower()
    if strategy not in ("type", "date"):
        strategy = "type"

    per_bucket: dict = {}
    moved = 0
    skipped = 0
    errors = []

    try:
        entries = os.listdir(target)
    except Exception as e:
        return f"ERROR: Cannot read '{target}'. {e}"

    for name in entries:
        src = os.path.join(target, name)
        # Only loose files; leave subfolders, hidden files and shortcuts in place.
        if not os.path.isfile(src):
            continue
        if name.startswith(".") or name.lower().endswith(".lnk"):
            skipped += 1
            continue

        if strategy == "date":
            try:
                bucket = datetime.datetime.fromtimestamp(os.path.getmtime(src)).strftime("%Y-%m")
            except Exception:
                bucket = "Unknown-Date"
        else:
            bucket = _category_for(os.path.splitext(name)[1])

        if dry_run:
            per_bucket[bucket] = per_bucket.get(bucket, 0) + 1
            moved += 1
            continue

        try:
            dest_dir = os.path.join(target, bucket)
            if not is_safe_path(dest_dir) or os.path.islink(dest_dir) or (
                hasattr(os.path, "isjunction") and os.path.isjunction(dest_dir)
            ):
                errors.append(f"{name}: unsafe destination folder")
                continue
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, _dedupe_path(os.path.join(dest_dir, name)))
            per_bucket[bucket] = per_bucket.get(bucket, 0) + 1
            moved += 1
        except Exception as e:
            errors.append(f"{name}: {e}")

    if moved == 0 and not errors:
        return (f"Nothing to organize in '{target}' — already tidy "
                f"(left {skipped} shortcuts/hidden files in place).")

    if errors and moved == 0:
        lines = [f"ERROR: Could not organize any files in '{target}' by {strategy}."]
    elif errors:
        lines = [f"PARTIAL: Organized {moved} files in '{target}' by {strategy}:"]
    else:
        verb = "Would organize" if dry_run else "Organized"
        lines = [f"✅ {verb} {moved} files in '{target}' by {strategy}:"]
    for bucket in sorted(per_bucket, key=lambda b: -per_bucket[b]):
        lines.append(f"  • {bucket}: {per_bucket[bucket]}")
    if skipped:
        lines.append(f"  (left {skipped} shortcuts/hidden files in place)")
    if errors:
        lines.append(f"  ⚠️ {len(errors)} could not move: " + "; ".join(errors[:3]))
    return "\n".join(lines)


def copy_file(src: str, dst: str) -> str:
    """Copy file or folder (cross-drive safe, auto-dedupe, parents created)."""
    if not os.path.exists(src):
        return f"ERR: missing {src}"
    dest = os.path.join(dst, os.path.basename(src)) if os.path.isdir(dst) else dst
    dest = _dedupe_path(dest)
    parent = os.path.dirname(dest)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    try:
        final = shutil.copytree(src, dest) if os.path.isdir(src) else shutil.copy2(src, dest)
        return f"OK: {final}"
    except Exception as e:
        return f"ERR: {src}->{dst} | {e}"


def create_folder(path: str) -> str:
    """Create directory (and parents). Returns error if already exists."""
    try:
        os.makedirs(path, exist_ok=False)
        return f"OK: {path}"
    except FileExistsError:
        return f"ERR: already exists: {path}"
    except Exception as e:
        return f"ERR: {e}"


def delete_folder(path: str) -> str:
    """Delete empty folder. Use force=True to delete recursively."""
    try:
        if not os.path.exists(path):
            return f"ERR: missing {path}"
        os.rmdir(path)
        return f"OK: removed {path}"
    except OSError:
        try:
            shutil.rmtree(path)
            return f"OK: removed {path} (recursive)"
        except Exception as e:
            return f"ERR: {e}"
    except Exception as e:
        return f"ERR: {e}"


# Directories to NEVER delete from
_SAFE_KEEP = {"c:\\windows", "c:\\program files", "c:\\program files (x86)", "c:\\programdata", "c:\\recovery"}
_MAYA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")).lower()


def _is_safe_to_delete(path: str) -> bool:
    """Check path is not in system/protected/Maya directory."""
    abspath = os.path.abspath(path).lower()
    for root in _SAFE_KEEP:
        if abspath.startswith(root):
            return False
    if abspath.startswith(_MAYA_DIR):
        return False
    return True


def _get_known_folders() -> list:
    """Get actual Desktop, Downloads, Documents paths (handles OneDrive redirection)."""
    import subprocess
    home = os.path.expanduser("~")
    try:
        ps = '[Environment]::GetFolderPath("Desktop") + "|" + [Environment]::GetFolderPath("MyDocuments") + "|" + [Environment]::GetFolderPath("MyPictures") + "|" + [Environment]::GetFolderPath("MyMusic") + "|" + [Environment]::GetFolderPath("MyVideos") + "|" + $env:TEMP + "|" + $env:USERPROFILE + "\\Downloads" + "|" + $env:USERPROFILE + "\\OneDrive\\Desktop"'
        r = subprocess.run(["powershell", "-NoProfile", ps], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            paths = [p for p in r.stdout.strip().split("|") if p and os.path.isdir(p)]
            if paths:
                return paths
    except Exception:
        pass
    # Fallback
    base = [os.path.join(home, d) for d in ("Desktop", "OneDrive\\Desktop", "Downloads", "Documents", "Pictures", "Music", "Videos")]
    base.append(os.environ.get("TEMP", os.path.join(home, "AppData", "Local", "Temp")))
    return [p for p in base if os.path.isdir(p)]


def _find_items(name: str, max_results: int) -> list:
    """Find files/folders matching `name` across user dirs + all drives (depth-limited)."""
    import string
    pattern = name.strip().lower()
    results = []
    # ── Priority 1: User profile dirs (fast, covers 95% of cases) ──
    priority = _get_known_folders()
    skip = {'appdata', 'node_modules', '.git', '__pycache__', '.cache'}
    for root in priority:
        if not os.path.isdir(root):
            continue
        try:
            for r, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d.lower() not in skip and not d.startswith('.')]
                if r.lower().startswith(_MAYA_DIR):
                    dirs.clear(); continue
                for entry in files + dirs:
                    if pattern in entry.lower():
                        results.append(os.path.join(r, entry))
                        if len(results) >= max_results:
                            return results
        except (PermissionError, OSError):
            pass
    if len(results) >= max_results:
        return results
    # ── Priority 2: Drive roots (depth=2, only user-writable dirs) ──
    sys_roots = {'windows', 'program files', 'program files (x86)', 'programdata',
                 '$recycle.bin', 'system volume information', 'recovery', 'boot'}
    for letter in string.ascii_uppercase:
        dr = f"{letter}:\\"
        if not os.path.exists(dr) or dr.lower().startswith("a:") or dr.lower().startswith("b:"):
            continue
        try:
            for item in os.listdir(dr):
                item_low = item.lower()
                if item_low in sys_roots or item.startswith('.'):
                    continue
                item_path = os.path.join(dr, item)
                if not os.path.isdir(item_path):
                    if pattern in item_low:
                        results.append(item_path)
                    continue
                # Walk 2 levels deep
                try:
                    for sub in os.listdir(item_path):
                        full = os.path.join(item_path, sub)
                        if pattern in sub.lower() and _is_safe_to_delete(full):
                            results.append(full)
                            if len(results) >= max_results:
                                return results
                        if os.path.isdir(full):
                            try:
                                for sub2 in os.listdir(full):
                                    f2 = os.path.join(full, sub2)
                                    if pattern in sub2.lower() and _is_safe_to_delete(f2):
                                        results.append(f2)
                                        if len(results) >= max_results:
                                            return results
                            except (PermissionError, OSError):
                                pass
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass
    return results


def delete_by_name(name: str, max_results: int = 5) -> str:
    """Find and delete file(s)/folder(s) by name across ALL drives.
    Searches user dirs first (Desktop, Downloads, Documents, Temp),
    then all drives (depth-limited). Skips system/protected dirs.
    max_results controls how many matching items to delete (default 5)."""
    name = name.strip()
    if not name:
        return "ERR: name cannot be empty"
    items = _find_items(name, max_results)
    if not items:
        return f"Not found: '{name}' anywhere on PC."
    deleted = []
    errors = []
    for path in items:
        if len(deleted) >= max_results:
            break
        if not os.path.exists(path):
            continue
        if not _is_safe_to_delete(path):
            errors.append(f"{os.path.basename(path)}: skipped (protected)")
            continue
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            deleted.append(path)
        except Exception as e:
            errors.append(f"{os.path.basename(path)}: {e}")
    parts = []
    if deleted:
        parts.append(f"Deleted {len(deleted)} item(s):")
        for d in deleted:
            parts.append(f"  - {d}")
    if errors:
        parts.append(f"Errors ({len(errors)}): {'; '.join(errors[:3])}")
    return "\n".join(parts) if parts else f"Not found: '{name}'."


def rename_file(src: str, new_name: str) -> str:
    """Rename file or folder within same directory."""
    parent = os.path.dirname(src) or "."
    dest = os.path.join(parent, new_name)
    dest = _dedupe_path(dest)
    try:
        os.rename(src, dest)
        return f"OK: {dest}"
    except Exception as e:
        return f"ERR: {e}"
