"""
Dynamic Skills Watcher — Hot-reloads Python skills into SKILLS_REGISTRY
without requiring a backend restart.

Addresses:
 1. Zombie modules  — removes from sys.modules before re-importing
 2. Race conditions — all registry mutations guarded by _registry_lock
 3. Syntax errors   — gracefully logged & skipped; watcher never crashes
"""

import sys
import importlib
import importlib.util
import threading
import logging
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

log = logging.getLogger(__name__)

# ── Thread-safe registry ───────────────────────────────────────────────────────
# Maps  skill_file_stem  →  list[callable]  (the tools exported by that skill)
SKILLS_REGISTRY: dict[str, list] = {}
_registry_lock = threading.Lock()

SKILLS_DIR = Path(__file__).parent          # backend/skills/
_OBSERVER: Observer | None = None

# Core framework files that should NEVER be loaded as dynamic skills
_CORE_FILES = {"loader", "md_loader", "scanner", "skill_watcher"}

# Trusted first-party skills that are allowed to use system modules (os, sys)
_TRUSTED_FILES = {"pc_optimizer"}


# ── Registry helpers ───────────────────────────────────────────────────────────

def get_dynamic_tools() -> list:
    """Return a flat list of all dynamically loaded skill tools (thread-safe)."""
    with _registry_lock:
        tools = []
        for tool_list in SKILLS_REGISTRY.values():
            tools.extend(tool_list)
        return tools


def _unload_skill(stem: str) -> None:
    """Remove a skill from the registry and purge its module from sys.modules."""
    with _registry_lock:
        SKILLS_REGISTRY.pop(stem, None)

    # Purge every submodule that belongs to this skill to prevent zombie objects
    prefix = f"maya_skill_{stem}"
    to_remove = [k for k in sys.modules if k == prefix or k.startswith(prefix + ".")]
    for key in to_remove:
        del sys.modules[key]


def _load_skill(path: Path) -> None:
    """
    Validate, import, and register a skill file.

    Steps
    -----
    1. Read source & run AST security scan (reuses existing scanner)
    2. Purge any stale module from sys.modules (zombie-prevention)
    3. Import via importlib using a unique module name
    4. Collect callables listed in  __maya_tools__  (or fallback: all callables)
    5. Store in SKILLS_REGISTRY under a lock
    """
    stem = path.stem
    
    # Do not load core framework files as dynamic skills
    if stem in _CORE_FILES:
        return

    # ── 1. Security scan (skip for trusted first-party skills) ────────────────
    if stem not in _TRUSTED_FILES:
        try:
            from backend.skills.scanner import scan_plugin_code, SecurityError
            code_str = path.read_text(encoding="utf-8")
            scan_plugin_code(code_str)          # raises ValueError (syntax) or SecurityError
        except (ValueError, Exception) as exc:
            log.warning(f"[SkillWatcher] Skipping '{path.name}': {exc}")
            return

    # ── 2. Zombie-prevention: remove old module before re-importing ───────────
    module_name = f"maya_skill_{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]

    # ── 3. Import ─────────────────────────────────────────────────────────────
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module   # register BEFORE exec (circular-safe)
        spec.loader.exec_module(module)
    except Exception as exc:
        log.warning(f"[SkillWatcher] Import error in '{path.name}': {exc}")
        sys.modules.pop(module_name, None)  # clean up on failure
        return

    # ── 4. Collect tools ──────────────────────────────────────────────────────
    if hasattr(module, "__maya_tools__"):
        # Preferred: explicit export list
        tools = [fn for fn in module.__maya_tools__ if callable(fn)]
    else:
        # Fallback: every public callable defined in the file
        tools = [
            obj for name, obj in vars(module).items()
            if callable(obj) and not name.startswith("_") and obj.__module__ == module_name
        ]

    if not tools:
        log.info(f"[SkillWatcher] '{path.name}' loaded but exported 0 tools — skipping registry.")
        return

    # ── 5. Thread-safe registry update ───────────────────────────────────────
    with _registry_lock:
        SKILLS_REGISTRY[stem] = tools

    log.info(f"[SkillWatcher] ✅ Loaded skill '{stem}' ({len(tools)} tool(s)): "
             f"{[fn.__name__ for fn in tools]}")


# ── Watchdog event handler ─────────────────────────────────────────────────────

class _SkillFileHandler(FileSystemEventHandler):

    def on_created(self, event):
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_deleted(self, event):
        if not event.is_directory:
            stem = Path(event.src_path).stem
            _unload_skill(stem)
            log.info(f"[SkillWatcher] 🗑️  Unloaded skill '{stem}'.")

    def on_moved(self, event):
        # Treat as: delete old name, add new name
        if not event.is_directory:
            _unload_skill(Path(event.src_path).stem)
            self._handle(Path(event.dest_path))

    @staticmethod
    def _handle(path: Path) -> None:
        if path.suffix == ".py" and not path.stem.startswith("_") and path.stem not in _CORE_FILES:
            _load_skill(path)


# ── Public lifecycle API ───────────────────────────────────────────────────────

def start_skill_watcher() -> None:
    """
    Bootstrap:
     1. Load every existing .py skill from SKILLS_DIR
     2. Spin up the watchdog Observer to hot-reload future changes
    """
    global _OBSERVER

    # Initial load of all existing skills
    for skill_file in sorted(SKILLS_DIR.glob("*.py")):
        if not skill_file.stem.startswith("_") and skill_file.stem not in _CORE_FILES:
            _load_skill(skill_file)

    # Start file-system watcher
    handler = _SkillFileHandler()
    _OBSERVER = Observer()
    _OBSERVER.schedule(handler, str(SKILLS_DIR), recursive=False)
    _OBSERVER.start()
    log.info(f"[SkillWatcher] 👀 Watching '{SKILLS_DIR}' for skill changes.")


def stop_skill_watcher() -> None:
    """Gracefully stop the watchdog Observer thread."""
    global _OBSERVER
    if _OBSERVER and _OBSERVER.is_alive():
        _OBSERVER.stop()
        _OBSERVER.join()
        log.info("[SkillWatcher] 🛑 Observer stopped.")
    _OBSERVER = None
