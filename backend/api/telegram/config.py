"""
telegram/config.py
==================
Configuration constants and utility functions for Telegram bot.

Extracted from telegram_bot.py to improve modularity and testability.
"""

import re
from typing import FrozenSet

# ──────────────────────────────────────────────────────────────────────────────
# API Configuration
# ──────────────────────────────────────────────────────────────────────────────

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# ──────────────────────────────────────────────────────────────────────────────
# Timing Constants
# ──────────────────────────────────────────────────────────────────────────────

EDIT_INTERVAL = 1.2  # seconds between live-edits (avoid Telegram flood)
STREAM_TIMEOUT = 60.0  # soft deadline before the task continues in background
BACKGROUND_TASK_TIMEOUT = 900.0  # hard ceiling for one Telegram task
TASK_STATUS_TTL = 900.0  # keep a backgrounded task's final status for 15 min
MANUAL_TIMEOUT = 300.0  # 5 min - auto-cancel WA manual reply
WA_EXPIRE_SECS = 1800  # 30 min — remove stale pending WA replies
WA_CLEANUP_INT = 300  # check every 5 min
MAX_EDIT_RETRIES = 3

# ──────────────────────────────────────────────────────────────────────────────
# Keyword Sets
# ──────────────────────────────────────────────────────────────────────────────

DANGEROUS_SHUTDOWN_KEYWORDS: FrozenSet[str] = frozenset([
    "shutdown", "shut down", "turn off", "bondho koro laptop",
    "laptop bondho", "shut", "শাটডাউন", "বন্ধ করো ল্যাপটপ",
])

SYSTEM_SCOPE_KEYWORDS: FrozenSet[str] = frozenset([
    "laptop", "pc", "computer", "system", "sob", "সব", "ল্যাপটপ",
])

SCREENSHOT_TRIGGER_KEYWORDS: FrozenSet[str] = frozenset([
    "dekho", "look", "screen", "screenshot", "chrome",
    "google", "browser", "youtube", "gmail",
])

STOP_KEYWORDS: FrozenSet[str] = frozenset([
    "stop", "halt", "panic", "🛑 emergency stop",
    "thamo", "থামো", "থাম",
])

APPROVAL_YES: FrozenSet[str] = frozenset({
    "yes", "y", "yeah", "yep", "হ্যাঁ", "হ্যা", "হা", "জি", "করো", "execute"
})

APPROVAL_NO: FrozenSet[str] = frozenset({
    "no", "n", "nope", "না", "cancel", "বাতিল", "করো না"
})

# ──────────────────────────────────────────────────────────────────────────────
# Regex Patterns
# ──────────────────────────────────────────────────────────────────────────────

_TASK_STATUS_RE = re.compile(
    r"(?:/task_status|/status|task status|job status|status(?: ki| dao| bolo)?"
    r"|progress(?: update| ki)?|update(?: dao| bolo)?)"
    r"|(?:ki holo|ki obostha|koto dur|hoyeche|complete hoyeche|done hoyeche)"
    r"|(?:(?:kaj|kaaj|task|job|eta|ota|pdf|email|mail)(?:\s*ta)?)"
    r"\s+(?:ki\s+)?(?:holo|hoyeche|complete|done|status|progress)",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────────

def is_task_status_request(text: str) -> bool:
    """
    Return True only for short messages asking about the current task.
    
    Args:
        text: User message text
        
    Returns:
        True if the message is a status request, False otherwise
    """
    normalized = re.sub(r"\s+", " ", (text or "").strip()).strip(" ?!.,")
    return len(normalized) <= 100 and bool(_TASK_STATUS_RE.fullmatch(normalized))
