"""
Maya AI — PC Optimizer Skill
Provides system health monitoring and safe junk file cleanup.
Works on Windows, macOS, and Linux.
"""
import os
import sys
import logging
import platform
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)


# ── Safe cleanup targets (user-owned only, no admin required) ────────────
def _get_temp_dirs() -> list[Path]:
    """Returns safe, user-owned temp directories for the current OS."""
    dirs = []

    if sys.platform == "win32":
        for key in ("TEMP", "TMP"):
            val = os.environ.get(key)
            if val:
                dirs.append(Path(val))

    elif sys.platform == "darwin":  # macOS
        dirs.append(Path.home() / "Library" / "Caches")
        tmp = os.environ.get("TMPDIR")
        if tmp:
            dirs.append(Path(tmp))

    else:  # Linux
        dirs.append(Path("/tmp"))
        xdg = os.environ.get("XDG_CACHE_HOME")
        if xdg:
            dirs.append(Path(xdg))
        else:
            dirs.append(Path.home() / ".cache")

    return [d for d in dirs if d.exists()]


# ── Internal helpers ─────────────────────────────────────────────────────
def _format_size(size_bytes: int) -> str:
    """Converts bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _get_all_disks() -> list[dict]:
    """
    Returns all mounted, real disks (excludes CD-ROM, snap, tmpfs, etc).
    Works on Windows, macOS, and Linux.
    """
    disks = []
    seen = set()

    for part in psutil.disk_partitions(all=False):
        # Skip duplicate mount points and unreadable drives (e.g. empty CD-ROM)
        if part.mountpoint in seen:
            continue
        # Skip virtual/non-physical filesystems on Linux
        if part.fstype in ("squashfs", "tmpfs", "devtmpfs", "overlay", ""):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mountpoint": part.mountpoint,
                "device": part.device,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            })
            seen.add(part.mountpoint)
        except (PermissionError, OSError):
            # Drive exists but is not readable (e.g. empty removable drive)
            pass

    return disks


def _calculate_folder_size(folder: Path) -> int:
    """Calculates total size of all files in a folder recursively."""
    total = 0
    try:
        for root, _, files in os.walk(folder):
            for f in files:
                path = Path(root) / f
                try:
                    total += path.stat().st_size
                except (PermissionError, FileNotFoundError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return total


def _safe_delete(folder: Path) -> int:
    """
    Deletes files one by one, skipping locked or permission-denied files.
    Uses topdown=False to clean empty subdirectories bottom-up.
    Returns total bytes freed.
    """
    freed = 0
    try:
        for root, dirs, files in os.walk(folder, topdown=False):
            # Delete files first
            for f in files:
                path = Path(root) / f
                try:
                    freed += path.stat().st_size
                    path.unlink()
                except (PermissionError, FileNotFoundError, OSError):
                    pass  # in-use or already deleted — skip

            # Remove empty subdirectories bottom-up
            for d in dirs:
                dir_path = Path(root) / d
                try:
                    dir_path.rmdir()  # only removes if empty
                except OSError:
                    pass  # not empty or permission issue — skip

    except (PermissionError, OSError) as e:
        logger.warning(f"Could not fully clean '{folder}': {e}")

    return freed


# ── Public Tool Functions ────────────────────────────────────────────────
def get_system_health() -> str:
    """
    Returns real-time PC health stats:
    CPU usage, RAM availability, and ALL disk drives free space.
    Works on Windows, macOS, and Linux.
    """
    try:
        cpu = psutil.cpu_percent(interval=1)

        ram = psutil.virtual_memory()
        ram_used_pct = ram.percent
        ram_available = _format_size(ram.available)

        os_name = platform.system()
        os_version = platform.release()

        lines = [
            f"🖥️ System Health ({os_name} {os_version})",
            f"CPU Usage    : {cpu}%",
            f"RAM Usage    : {ram_used_pct}% used | {ram_available} available",
            f"",
            f"💾 Disk Drives:",
        ]

        disks = _get_all_disks()
        if disks:
            for disk in disks:
                label = disk["mountpoint"]
                lines.append(
                    f"  {label:<10} "
                    f"{_format_size(disk['free'])} free / "
                    f"{_format_size(disk['total'])} total "
                    f"({disk['percent']}% used)"
                )
        else:
            lines.append("  No readable drives found.")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        return f"ERROR: Could not retrieve system health. {e}"


def preview_junk_cleanup() -> str:
    """
    Scans temp directories and shows how much space WOULD be freed.
    Does NOT delete anything. Use before calling clean_system_junk().
    """
    try:
        temp_dirs = _get_temp_dirs()
        if not temp_dirs:
            return "INFO: No temp directories found on this system."

        total = 0
        lines = ["🔍 Junk Preview (no files deleted yet):"]
        for d in temp_dirs:
            size = _calculate_folder_size(d)
            total += size
            lines.append(f"  {d} → {_format_size(size)}")

        lines.append(f"\nTotal freeable: {_format_size(total)}")
        lines.append("Say 'clean my PC' to confirm deletion.")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error during junk preview: {e}")
        return f"ERROR: Could not preview junk files. {e}"


def clean_system_junk(confirmed: bool = False) -> str:
    """
    Safely deletes temporary/junk files from user-owned temp directories.
    Skips locked or permission-denied files without crashing.

    Args:
        confirmed: Must be True to actually delete. If False, runs preview only.

    Returns:
        A summary string of freed space or a confirmation prompt.
    """
    if not confirmed:
        return (
            preview_junk_cleanup() +
            "\n⚠️ To confirm deletion, call clean_system_junk(confirmed=True)."
        )

    try:
        temp_dirs = _get_temp_dirs()
        if not temp_dirs:
            return "INFO: No temp directories found on this system."

        total_freed = 0
        lines = ["🧹 Cleanup Complete:"]
        for d in temp_dirs:
            freed = _safe_delete(d)
            total_freed += freed
            lines.append(f"  {d} → freed {_format_size(freed)}")

        lines.append(f"\n✅ Total freed: {_format_size(total_freed)}")
        logger.info(f"Junk cleanup complete. Freed: {_format_size(total_freed)}")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error during junk cleanup: {e}")
        return f"ERROR: Cleanup failed. {e}"


# ── Tool Registry ────────────────────────────────────────────────────────
__maya_tools__ = [
    get_system_health,
    preview_junk_cleanup,
    clean_system_junk,
]
