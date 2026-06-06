"""
Maya SKILL.md Loader — Markdown-based skill system.

How it works:
  1. Each skill lives in its own folder:  builtin/<name>/SKILL.md
                                          user_skills/<name>/SKILL.md
  2. SKILL.md has YAML frontmatter (name, description, priority) + markdown body.
  3. At startup all skills are loaded into MD_SKILLS_REGISTRY (thread-safe).
  4. get_skills_prompt_block() builds a markdown block injected into the agent
     system prompt — Maya "learns" new workflows without a restart.
  5. Watchdog hot-reloads any SKILL.md that is created / modified / deleted.

Priority (highest wins on name conflict):
  user_skills  >  builtin

Design:
  • Standard SKILL.md format and precedence model
  • Maya-specific: skills are injected per-session at orchestrator level
  • Builtin skills only cover workflows NOT already in maya_personality.py
"""

import yaml
import threading
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Directories ───────────────────────────────────────────────────────────────
_BASE = Path(__file__).parent
SKILLS_BUILTIN_DIR  = _BASE / "builtin"
SKILLS_USER_DIR     = _BASE / "user_skills"

# ── Thread-safe registry ──────────────────────────────────────────────────────
# Maps  skill_name  →  {name, description, instructions, path, priority}
MD_SKILLS_REGISTRY: dict[str, dict] = {}
_lock = threading.Lock()

_OBSERVER = None   # watchdog observer (set by start_md_skill_loader)


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_skill_md(path: Path) -> Optional[dict]:
    """
    Parse a SKILL.md file.
    Returns dict with: name, description, instructions, path, priority
    Returns None on any error.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning(f"[MD-Skills] Cannot read '{path}': {exc}")
        return None

    frontmatter: dict = {}
    body: str = content.strip()

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                if isinstance(fm, dict):
                    frontmatter = fm
                body = parts[2].strip()
            except Exception as exc:
                log.warning(f"[MD-Skills] YAML error in '{path}': {exc}")
                return None

    # Infer name: frontmatter > parent directory name
    name: str = str(frontmatter.get("name") or path.parent.name).strip()
    if not name:
        log.warning(f"[MD-Skills] No name found in '{path}' — skipping.")
        return None

    description: str = str(frontmatter.get("description") or "").strip()
    # Disable flag — set disable: true in frontmatter to skip a skill
    if frontmatter.get("disable"):
        log.info(f"[MD-Skills] Skill '{name}' is disabled — skipping.")
        return None

    return {
        "name":         name,
        "description":  description,
        "instructions": body,
        "path":         str(path),
        "priority":     int(frontmatter.get("priority", 0)),
        "emoji":        str(frontmatter.get("emoji") or "🛠️"),
    }


# ── Registry helpers ──────────────────────────────────────────────────────────

def _register(path: Path, source_priority: int) -> None:
    """Parse and register a single SKILL.md, respecting priority."""
    if path.name != "SKILL.md":
        return
    skill = parse_skill_md(path)
    if not skill:
        return

    effective_priority = skill["priority"] + source_priority
    name = skill["name"]

    with _lock:
        existing = MD_SKILLS_REGISTRY.get(name)
        if existing and existing["priority"] >= effective_priority:
            log.debug(f"[MD-Skills] Skipping '{name}' — higher-priority version loaded.")
            return
        skill["priority"] = effective_priority
        MD_SKILLS_REGISTRY[name] = skill

    log.info(f"[MD-Skills] ✅ Loaded skill '{name}' (priority={effective_priority}) ← {path}")


def _unregister_by_path(path: Path) -> None:
    """Remove any skill whose SKILL.md path matches."""
    with _lock:
        victims = [k for k, v in MD_SKILLS_REGISTRY.items()
                   if v["path"] == str(path)]
        for k in victims:
            del MD_SKILLS_REGISTRY[k]
            log.info(f"[MD-Skills] 🗑️  Unloaded skill '{k}'")


def _scan_dir(directory: Path, source_priority: int) -> None:
    """Recursively scan a directory for SKILL.md files."""
    if not directory.exists():
        return
    for skill_md in sorted(directory.rglob("SKILL.md")):
        _register(skill_md, source_priority)


# ── Prompt builder ────────────────────────────────────────────────────────────

def get_skills_prompt_block() -> str:
    """
    Return a markdown block ready to be appended to Maya's system prompt.
    Empty string if no skills are loaded.

    Format:
    ---
    ## 🛠️ Maya Skills
    ### <emoji> <name>
    _<description>_
    <instructions>
    ---
    """
    with _lock:
        skills = sorted(MD_SKILLS_REGISTRY.values(),
                        key=lambda s: (-s["priority"], s["name"]))

    if not skills:
        return ""

    lines = [
        "",
        "---",
        "## 🛠️ Maya Skills — Active Workflows",
        "_The following skill instructions extend your capabilities. "
        "Follow them precisely when the user's request matches._",
        "",
    ]
    for skill in skills:
        emoji = skill.get("emoji", "🛠️")
        lines.append(f"### {emoji} {skill['name']}")
        if skill["description"]:
            lines.append(f"_{skill['description']}_")
            lines.append("")
        if skill["instructions"]:
            lines.append(skill["instructions"])
            lines.append("")

    lines.append("---")
    return "\n".join(lines)


def get_loaded_skills() -> list[dict]:
    """Return a snapshot of all loaded skills (for debug/API endpoints)."""
    with _lock:
        return [
            {k: v for k, v in s.items() if k != "instructions"}
            for s in MD_SKILLS_REGISTRY.values()
        ]


# ── Watchdog handler ──────────────────────────────────────────────────────────

def _make_handler(source_priority: int):
    """Factory: create a watchdog FileSystemEventHandler for a given priority."""
    from watchdog.events import FileSystemEventHandler  # local import — optional dep

    class _SkillMDHandler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory:
                _register(Path(event.src_path), source_priority)

        def on_modified(self, event):
            if not event.is_directory:
                p = Path(event.src_path)
                _unregister_by_path(p)
                _register(p, source_priority)

        def on_deleted(self, event):
            if not event.is_directory:
                _unregister_by_path(Path(event.src_path))

        def on_moved(self, event):
            if not event.is_directory:
                _unregister_by_path(Path(event.src_path))
                _register(Path(event.dest_path), source_priority)

    return _SkillMDHandler()


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def start_md_skill_loader() -> None:
    """
    Bootstrap the SKILL.md system:
      1. Ensure user_skills/ directory exists (with a helpful README)
      2. Scan builtin/ (priority=0) then user_skills/ (priority=10)
      3. Start watchdog observer to hot-reload on file changes
    """
    global _OBSERVER

    # Ensure user_skills dir exists
    SKILLS_USER_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_user_readme()

    # Initial scan — builtin first (lower priority), user second (higher)
    _scan_dir(SKILLS_BUILTIN_DIR, source_priority=0)
    _scan_dir(SKILLS_USER_DIR,    source_priority=10)

    n = len(MD_SKILLS_REGISTRY)
    log.info(f"[MD-Skills] 🚀 Loaded {n} skill(s) at startup.")

    # Start watchdog
    try:
        from watchdog.observers import Observer
        _OBSERVER = Observer()

        watch_dirs = [
            (SKILLS_BUILTIN_DIR, 0),
            (SKILLS_USER_DIR,   10),
        ]
        for watch_dir, prio in watch_dirs:
            watch_dir.mkdir(parents=True, exist_ok=True)
            _OBSERVER.schedule(_make_handler(prio), str(watch_dir), recursive=True)

        _OBSERVER.start()
        log.info("[MD-Skills] 👀 Watching builtin/ and user_skills/ for SKILL.md changes.")
    except ImportError:
        log.warning("[MD-Skills] watchdog not installed — hot-reload disabled.")
    except Exception as exc:
        log.error(f"[MD-Skills] Watcher error: {exc}")


def stop_md_skill_loader() -> None:
    """Gracefully stop the watchdog observer."""
    global _OBSERVER
    if _OBSERVER and _OBSERVER.is_alive():
        _OBSERVER.stop()
        _OBSERVER.join()
        log.info("[MD-Skills] 🛑 Stopped.")
    _OBSERVER = None


# ── User README auto-create ───────────────────────────────────────────────────

def _ensure_user_readme() -> None:
    readme = SKILLS_USER_DIR / "README.md"
    if readme.exists():
        return
    readme.write_text(
        "# 🛠️ Maya User Skills\n\n"
        "Place your custom markdown-based skills in this folder.\n\n"
        "## How to Create a New Skill?\n\n"
        "1. Create a new subdirectory inside user_skills/:\n"
        "   ```\n"
        "   user_skills/\n"
        "     my_skill/\n"
        "       SKILL.md\n"
        "   ```\n\n"
        "2. Add your instructions to the `SKILL.md` file:\n"
        "   ```markdown\n"
        "   ---\n"
        "   name: my_skill\n"
        "   description: My custom skill description\n"
        "   emoji: 🎯\n"
        "   priority: 10\n"
        "   ---\n\n"
        "   ## Instructions\n\n"
        "   When the user says:\n"
        "   - \"trigger phrase 1\"\n"
        "   - \"trigger phrase 2\"\n\n"
        "   Follow this workflow:\n"
        "   1. First, do X\n"
        "   2. Then, do Y\n"
        "   ```\n\n"
        "3. Save the file — Maya will hot-reload and load it automatically! ♻️\n\n"
        "## Tips\n"
        "- Add `disable: true` in the frontmatter to temporarily disable a skill.\n"
        "- Increase `priority: 20` to override default builtin skills with the same name.\n"
        "- You can ask Maya \"create a new skill\" and she will guide you through the process.\n",
        encoding="utf-8",
    )
    log.info("[MD-Skills] 📝 Created user_skills/README.md")
