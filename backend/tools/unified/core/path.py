"""Unified path resolution — dedupe, known folders, search."""
import os, subprocess, string


MAX_SEARCH_RESULTS = 50


def dedupe_path(dest: str) -> str:
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def get_known_folders() -> list:
    """Actual Desktop/Downloads/Documents paths (handles OneDrive)."""
    try:
        ps = ('[Environment]::GetFolderPath("Desktop")+"|"+[Environment]::GetFolderPath("MyDocuments")+"|"'
              '+[Environment]::GetFolderPath("MyPictures")+"|"+[Environment]::GetFolderPath("MyMusic")+"|"'
              '+[Environment]::GetFolderPath("MyVideos")+"|"+$env:TEMP+"|"+$env:USERPROFILE+"\\Downloads"+"|"+$env:USERPROFILE+"\\OneDrive\\Desktop"')
        r = subprocess.run(["powershell", "-NoProfile", ps], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            paths = [p for p in r.stdout.strip().split("|") if p and os.path.isdir(p)]
            if paths:
                return paths
    except Exception:
        pass
    home = os.path.expanduser("~")
    base = [os.path.join(home, d) for d in ("Desktop", "OneDrive\\Desktop", "Downloads", "Documents", "Pictures", "Music", "Videos")]
    base.append(os.environ.get("TEMP", os.path.join(home, "AppData", "Local", "Temp")))
    return [p for p in base if os.path.isdir(p)]


def normalize_search(name: str, max_results: int = 5) -> tuple[str, int]:
    """Validate search arguments before scanning any filesystem roots."""
    pattern = str(name or "").strip().lower()
    if not pattern:
        raise ValueError("name cannot be empty")
    try:
        limit = int(max_results)
    except (TypeError, ValueError) as exc:
        raise ValueError("n must be an integer") from exc
    if limit < 1 or limit > MAX_SEARCH_RESULTS:
        raise ValueError(f"n must be between 1 and {MAX_SEARCH_RESULTS}")
    return pattern, limit


def find_items(name: str, max_results: int = 5) -> list:
    """Find files/folders by name across user dirs + all drives (depth-limited)."""
    pattern, max_results = normalize_search(name, max_results)
    results = []
    seen = set()

    def add_result(path: str) -> bool:
        from .policy import is_safe_path

        if not is_safe_path(path):
            return False
        key = os.path.normcase(os.path.realpath(os.path.abspath(path)))
        if key in seen:
            return False
        seen.add(key)
        results.append(path)
        return len(results) >= max_results
    for root in get_known_folders():
        try:
            for r, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d.lower() not in {'appdata','node_modules','.git','__pycache__','.cache'} and not d.startswith('.')]
                for entry in files + dirs:
                    if pattern in entry.lower():
                        full = os.path.join(r, entry)
                        if add_result(full):
                            return results
        except (PermissionError, OSError):
            pass
    if len(results) >= max_results:
        return results
    sys_roots = {'windows', 'program files', 'program files (x86)', 'programdata', '$recycle.bin', 'system volume information', 'recovery', 'boot'}
    for letter in string.ascii_uppercase:
        dr = f"{letter}:\\"
        if not os.path.exists(dr) or dr.lower().startswith(("a:", "b:")):
            continue
        try:
            for item in os.listdir(dr):
                item_low = item.lower()
                if item_low in sys_roots or item.startswith('.'):
                    continue
                item_path = os.path.join(dr, item)
                if not os.path.isdir(item_path):
                    if pattern in item_low and add_result(item_path):
                        return results
                    continue
                try:
                    for sub in os.listdir(item_path):
                        full = os.path.join(item_path, sub)
                        if pattern in sub.lower() and add_result(full):
                            return results
                        if os.path.isdir(full):
                            try:
                                for sub2 in os.listdir(full):
                                    f2 = os.path.join(full, sub2)
                                    if pattern in sub2.lower() and add_result(f2):
                                        return results
                            except (PermissionError, OSError):
                                pass
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass
    return results
