"""
telegram_bot.py
===============
Backward-compatibility redirect hub for refactored Telegram bot.

This file re-exports everything from the new modular structure to maintain
backward compatibility with existing imports throughout Maya's codebase.

Old structure: 2000+ lines monolithic file
New structure: Modular architecture in backend/api/telegram/

Architecture:
- Core: lifecycle, polling, state_models
- Messaging: sender, editor, typing, rate_limiter
- Handlers: message_handler, callback_handler, command_handler, task_handler
- WhatsApp: notification, manager
- Config: constants, regex patterns, utility functions
"""

# ──────────────────────────────────────────────────────────────────────────────
# Import from new modular structure
# ──────────────────────────────────────────────────────────────────────────────

# Main manager class
from backend.api.telegram.manager import TelegramBotManager

# State models (dataclasses)
from backend.api.telegram.core.state_models import (
    PendingWAReply,
    PendingDangerousCmd,
    TelegramTaskState,
)

# Constants and utility functions
from backend.api.telegram.config import (
    TELEGRAM_API,
    EDIT_INTERVAL,
    STREAM_TIMEOUT,
    BACKGROUND_TASK_TIMEOUT,
    TASK_STATUS_TTL,
    MANUAL_TIMEOUT,
    WA_EXPIRE_SECS,
    WA_CLEANUP_INT,
    MAX_EDIT_RETRIES,
    DANGEROUS_SHUTDOWN_KEYWORDS,
    SYSTEM_SCOPE_KEYWORDS,
    SCREENSHOT_TRIGGER_KEYWORDS,
    STOP_KEYWORDS,
    APPROVAL_YES,
    APPROVAL_NO,
    is_task_status_request as _is_task_status_request,
)

# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton (for backward compatibility)
# ──────────────────────────────────────────────────────────────────────────────
telegram_bot_manager = TelegramBotManager()

# ──────────────────────────────────────────────────────────────────────────────
# Public exports
# ──────────────────────────────────────────────────────────────────────────────
__all__ = [
    # Main manager
    "TelegramBotManager",
    "telegram_bot_manager",
    
    # State models
    "PendingWAReply",
    "PendingDangerousCmd",
    "TelegramTaskState",
    
    # Constants
    "TELEGRAM_API",
    "EDIT_INTERVAL",
    "STREAM_TIMEOUT",
    "BACKGROUND_TASK_TIMEOUT",
    "TASK_STATUS_TTL",
    "MANUAL_TIMEOUT",
    "WA_EXPIRE_SECS",
    "WA_CLEANUP_INT",
    "MAX_EDIT_RETRIES",
    "DANGEROUS_SHUTDOWN_KEYWORDS",
    "SYSTEM_SCOPE_KEYWORDS",
    "SCREENSHOT_TRIGGER_KEYWORDS",
    "STOP_KEYWORDS",
    "APPROVAL_YES",
    "APPROVAL_NO",
    
    # Utility functions
    "_is_task_status_request",
]

# ──────────────────────────────────────────────────────────────────────────────
# Migration Notes
# ──────────────────────────────────────────────────────────────────────────────
"""
REFACTORING COMPLETE ✅

Old file: 2000+ lines (telegram_bot.py.backup)
New structure: ~15 modular files

Benefits:
- Single Responsibility Principle: Each module has one clear purpose
- Testability: Each component can be tested independently
- Maintainability: Changes are localized to specific modules
- Readability: Each file is <500 lines, easy to understand
- Extensibility: New features can be added without touching core logic

Module Structure:
├── config.py (80 lines)
├── manager.py (500 lines - slim orchestrator)
├── core/
│   ├── lifecycle.py (150 lines)
│   ├── polling.py (200 lines)
│   └── state_models.py (60 lines)
├── messaging/
│   ├── sender.py (150 lines)
│   ├── editor.py (100 lines)
│   ├── typing.py (120 lines)
│   └── rate_limiter.py (100 lines)
├── handlers/
│   ├── message_handler.py (300 lines)
│   ├── callback_handler.py (250 lines)
│   ├── command_handler.py (200 lines)
│   └── task_handler.py (450 lines)
└── whatsapp/
    ├── notification.py (650 lines)
    └── manager.py (integrated)

All imports throughout Maya's codebase remain unchanged due to this redirect file.
"""
