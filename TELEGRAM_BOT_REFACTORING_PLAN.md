# Telegram Bot Refactoring Plan

## Executive Summary

**Current State:** `backend/api/telegram_bot.py` is 2000+ lines with 50+ methods handling lifecycle, message routing, WhatsApp integration, callbacks, and utilities.

**Goal:** Split into modular components for better maintainability, testing, and code organization.

**Target Structure:** 15-20 focused modules, each ~100-200 lines, organized by responsibility.

**Migration Strategy:** Gradual refactoring with backward compatibility, comprehensive testing at each step.

---

## Current Analysis

### File Statistics
- **Total Lines:** ~2000
- **Classes:** 4 (PendingWAReply, PendingDangerousCmd, TelegramTaskState, TelegramBotManager)
- **Methods:** 50+ methods in TelegramBotManager
- **Dependencies:** 
  - httpx (HTTP client)
  - backend.database (config, crypto)
  - backend.brain (orchestrator, language, tool_planner)
  - backend.system (process_manager)
  - backend.vision (screen_capture)

### Identified Concerns (Logical Groupings)

1. **Lifecycle Management** (5 methods)
2. **Message Handling** (6 methods)
3. **Callback Query Handling** (9 methods)
4. **WhatsApp Integration** (15 methods)
5. **Messaging/Communication** (7 methods)
6. **State Management** (4 classes + 5 methods)
7. **Command Handlers** (8 static commands)
8. **Utilities** (polling, screenshot, keyboard)
9. **Safety/Approval** (dangerous command confirmation, tool approval)
10. **Configuration** (constants, regex patterns)

---

## Proposed Architecture

```
backend/api/telegram/
├── __init__.py                    # Public exports
├── manager.py                     # TelegramBotManager (orchestrator)
├── config.py                      # Constants, API URL, regex patterns
│
├── core/
│   ├── __init__.py
│   ├── lifecycle.py               # start(), stop(), restart(), load_config()
│   ├── polling.py                 # _poll_loop(), _claim_update()
│   └── state_models.py            # Dataclasses (PendingWAReply, etc.)
│
├── handlers/
│   ├── __init__.py
│   ├── message_handler.py         # _handle_message(), routing logic
│   ├── callback_handler.py        # _handle_callback_query(), button routing
│   ├── command_handler.py         # Static commands (/start, /help, /status)
│   ├── task_handler.py            # _process_and_reply(), task orchestration
│   └── approval_handler.py        # Tool approval, dangerous command confirmation
│
├── whatsapp/
│   ├── __init__.py
│   ├── notification.py            # _handle_whatsapp_incoming()
│   ├── callbacks.py               # _wa_cb_* methods (gemini, send, manual, etc.)
│   ├── pairing.py                 # _handle_wa_pair(), _is_wa_pair_command()
│   ├── manual_reply.py            # Manual reply flow, timers
│   ├── authorization.py           # _require_wa_reply_authorization(), allow/block
│   └── ui_copy.py                 # _wa_ui_copy(), language-specific messages
│
├── messaging/
│   ├── __init__.py
│   ├── sender.py                  # _send_message(), _send_message_get_id()
│   ├── editor.py                  # _edit_message()
│   ├── formatter.py               # Markdown handling, error formatting
│   ├── rate_limiter.py            # _post_with_retry(), backoff logic
│   └── typing.py                  # _send_typing(), _send_screenshot()
│
├── state/
│   ├── __init__.py
│   ├── task_state.py              # TelegramTaskState management
│   ├── wa_state.py                # WhatsApp pending state management
│   └── language_style.py          # _remember_chat_language_style()
│
└── utils/
    ├── __init__.py
    ├── keyboard.py                # _default_keyboard()
    ├── detection.py               # _is_dangerous_shutdown(), _detect_language_hint()
    └── process_cleanup.py         # _clean_duplicate_processes()
```

---

## Detailed Module Breakdown

### 1. `config.py` - Configuration & Constants

**Purpose:** Centralize all constants, patterns, and configuration values.

**Contents:**
- API URL template
- Timeout constants (EDIT_INTERVAL, STREAM_TIMEOUT, etc.)
- Keyword sets (DANGEROUS_SHUTDOWN_KEYWORDS, STOP_KEYWORDS, etc.)
- Regex patterns (_TASK_STATUS_RE)
- Helper: `_is_task_status_request(text)`

**Example:**
```python
"""Telegram bot configuration and constants."""

import re
from typing import FrozenSet

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Timing constants
EDIT_INTERVAL = 1.2
STREAM_TIMEOUT = 60.0
BACKGROUND_TASK_TIMEOUT = 900.0
TASK_STATUS_TTL = 900.0
MANUAL_TIMEOUT = 300.0
WA_EXPIRE_SECS = 1800
WA_CLEANUP_INT = 300
MAX_EDIT_RETRIES = 3

# Command keywords
DANGEROUS_SHUTDOWN_KEYWORDS: FrozenSet[str] = frozenset([
    "shutdown", "shut down", "turn off", "bondho koro laptop",
    "laptop bondho", "shut", "শাটডাউন", "বন্ধ করো ল্যাপটপ",
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

# Patterns
_TASK_STATUS_RE = re.compile(r"...", re.IGNORECASE)

def is_task_status_request(text: str) -> bool:
    """Check if text is a task status query."""
    normalized = re.sub(r"\s+", " ", (text or "").strip()).strip(" ?!.,")
    return len(normalized) <= 100 and bool(_TASK_STATUS_RE.fullmatch(normalized))
```

**Lines:** ~80-100

---

### 2. `core/state_models.py` - State Data Classes

**Purpose:** Define typed state containers.

**Contents:**
- `PendingWAReply` dataclass
- `PendingDangerousCmd` dataclass
- `TelegramTaskState` dataclass

**Example:**
```python
"""State models for Telegram bot."""

from dataclasses import dataclass, field
import time

@dataclass
class PendingWAReply:
    """Holds all state for one incoming WhatsApp message awaiting action."""
    id: str
    chat_id_wa: str
    from_number: str
    from_name: str
    is_group: bool
    group_name: str
    trigger_msg: str
    context_messages: list
    is_known: bool
    gemini_draft: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class PendingDangerousCmd:
    """Confirmation state for a dangerous command."""
    telegram_chat_id: str
    original_text: str


@dataclass
class TelegramTaskState:
    """Progress snapshot for the latest orchestrator task in one chat."""
    original_text: str
    session_id: str
    started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    state: str = "running"
    active_agent: str = ""
    status: str = "Starting task..."
    backgrounded: bool = False
    final_text: str = ""
    error: str = ""
```

**Lines:** ~50

---

### 3. `core/lifecycle.py` - Bot Lifecycle

**Purpose:** Handle bot startup, shutdown, configuration loading.

**Contents:**
- `load_config()` - Read from database
- `start()` - Initialize HTTP client, spawn tasks
- `stop()` - Cancel tasks, cleanup resources
- `restart()` - Combined stop/start

**Dependencies:**
- `backend.database.connection`
- `backend.database.crypto`
- `backend.database.models`
- `httpx`

**Example:**
```python
"""Telegram bot lifecycle management."""

import asyncio
import logging
from typing import Optional
import httpx

from backend.database.connection import SessionLocal
from backend.database.crypto import crypto_manager, KeyUnreadableError
from backend.database.models import UserPreferences

logger = logging.getLogger(__name__)

class LifecycleManager:
    """Manages Telegram bot lifecycle."""
    
    def __init__(self, manager):
        self.manager = manager  # Reference to TelegramBotManager
        
    def load_config(self) -> None:
        """Load configuration from database."""
        db = SessionLocal()
        try:
            def _get(key: str) -> Optional[str]:
                pref = db.query(UserPreferences).filter(
                    UserPreferences.key == key
                ).first()
                if not pref or not pref.value:
                    return None
                try:
                    return crypto_manager.decrypt(pref.value, raise_on_failure=True)
                except KeyUnreadableError:
                    return None
                    
            self.manager.enabled = _get("TELEGRAM_BOT_ENABLED") == "true"
            self.manager.bot_token = _get("TELEGRAM_BOT_TOKEN")
            self.manager.chat_id = _get("TELEGRAM_CHAT_ID")
            # ... pairing code generation logic
        finally:
            db.close()
            
    def start(self) -> None:
        """Start the bot."""
        # Implementation
        
    async def stop(self) -> None:
        """Stop the bot gracefully."""
        # Implementation
        
    async def restart(self) -> None:
        """Restart the bot."""
        await self.stop()
        self.start()
```

**Lines:** ~150-180

---

### 4. `core/polling.py` - Update Polling

**Purpose:** Handle Telegram API long-polling.

**Contents:**
- `_poll_loop()` - Main polling loop
- `_claim_update()` - Deduplication logic
- Update dispatch to handlers

**Example:**
```python
"""Telegram API polling logic."""

import asyncio
import logging
from collections import deque
from typing import Optional, Callable, Awaitable
import httpx

from .config import TELEGRAM_API

logger = logging.getLogger(__name__)

class PollingManager:
    """Manages Telegram update polling."""
    
    def __init__(self, manager):
        self.manager = manager
        self._seen_update_ids: deque[int] = deque(maxlen=2048)
        self._seen_update_id_set: set[int] = set()
        
    def _claim_update(self, update_id: int) -> bool:
        """Return False if already processed."""
        if update_id in self._seen_update_id_set:
            return False
        if len(self._seen_update_ids) == self._seen_update_ids.maxlen:
            oldest = self._seen_update_ids.popleft()
            self._seen_update_id_set.discard(oldest)
        self._seen_update_ids.append(update_id)
        self._seen_update_id_set.add(update_id)
        return True
        
    async def poll_loop(
        self,
        http_client: httpx.AsyncClient,
        on_message: Callable,
        on_callback: Callable
    ) -> None:
        """Main polling loop."""
        offset: Optional[int] = None
        retry_delay = 1.0
        
        while self.manager.running:
            if not self.manager.bot_token:
                await asyncio.sleep(5.0)
                continue
            try:
                params = {"timeout": 20}
                if offset:
                    params["offset"] = offset
                    
                resp = await http_client.get(
                    TELEGRAM_API.format(
                        token=self.manager.bot_token,
                        method="getUpdates"
                    ),
                    params=params,
                )
                
                if resp.status_code == 200:
                    for update in resp.json().get("result", []):
                        offset = update["update_id"] + 1
                        if not self._claim_update(update["update_id"]):
                            continue
                        if cq := update.get("callback_query"):
                            asyncio.create_task(on_callback(cq))
                        elif msg := update.get("message"):
                            asyncio.create_task(on_message(msg))
                # ... error handling
            except Exception as exc:
                logger.error("Poll error: %s", exc)
                await asyncio.sleep(retry_delay)
```

**Lines:** ~120-150

---

### 5. `handlers/message_handler.py` - Message Routing

**Purpose:** Route incoming messages to appropriate handlers.

**Contents:**
- `_handle_message()` - Main message dispatcher
- Pairing check
- Authorization check
- Command routing
- Task status requests
- Approval interception

**Example:**
```python
"""Message handling and routing."""

import asyncio
import logging
from typing import TYPE_CHECKING

from ..config import (
    STOP_KEYWORDS, APPROVAL_YES, APPROVAL_NO,
    is_task_status_request
)

if TYPE_CHECKING:
    from ..manager import TelegramBotManager

logger = logging.getLogger(__name__)

class MessageHandler:
    """Handles incoming Telegram messages."""
    
    def __init__(self, manager: 'TelegramBotManager'):
        self.manager = manager
        
    async def handle_message(self, message: dict) -> None:
        """Route message to appropriate handler."""
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()
        if not text:
            return
            
        # Check for manual WA reply intercept
        if pending_id := self.manager._wa_manual_awaiting.get(chat_id):
            if self.manager.chat_id and chat_id == self.manager.chat_id:
                await self.manager.whatsapp.complete_manual_reply(
                    chat_id, pending_id, text
                )
                return
                
        # Pairing handshake
        if not self.manager.chat_id:
            await self.manager.commands.handle_pairing(chat_id, text)
            return
            
        # Authorization check
        if chat_id != self.manager.chat_id:
            await self.manager.messaging.send_message(
                chat_id,
                "❌ *Unauthorized.* This Maya AI instance is paired."
            )
            return
            
        # Remember language style
        self.manager.state.remember_language_style(chat_id, text)
        text_lower = text.lower()
        
        # Tool approval handling
        if self._handle_approval(chat_id, text_lower):
            return
            
        # Task status requests
        if is_task_status_request(text):
            if await self._handle_status_check(chat_id):
                return
                
        # WhatsApp pairing command
        if self.manager.whatsapp.is_pair_command(text_lower):
            await self.manager.whatsapp.handle_pairing(chat_id, text)
            return
            
        # Static commands
        if await self.manager.commands.handle_static_command(
            chat_id, text_lower
        ):
            return
            
        # Emergency stop
        if text_lower in STOP_KEYWORDS:
            await self.manager.commands.emergency_stop(chat_id)
            return
            
        # Route to orchestrator
        await self._route_to_orchestrator(chat_id, text)
        
    def _handle_approval(self, chat_id: str, text_lower: str) -> bool:
        """Handle approval responses. Returns True if handled."""
        # Implementation
        return False
        
    async def _handle_status_check(self, chat_id: str) -> bool:
        """Handle status requests. Returns True if handled."""
        # Implementation
        return False
        
    async def _route_to_orchestrator(self, chat_id: str, text: str) -> None:
        """Send message to brain orchestrator."""
        # Implementation
```

**Lines:** ~180-220

---

### 6. `handlers/callback_handler.py` - Callback Query Routing

**Purpose:** Handle inline button callbacks.

**Contents:**
- `_handle_callback_query()` - Main dispatcher
- Authorization checks
- Route to WhatsApp callbacks
- Route to approval callbacks
- Route to shutdown confirmation

**Example:**
```python
"""Callback query handling."""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..manager import TelegramBotManager

logger = logging.getLogger(__name__)

class CallbackHandler:
    """Handles Telegram callback queries (inline buttons)."""
    
    def __init__(self, manager: 'TelegramBotManager'):
        self.manager = manager
        
    async def handle_callback_query(self, cq: dict) -> None:
        """Route callback to appropriate handler."""
        cq_id = cq.get("id")
        data = cq.get("data", "")
        chat_id = str(cq["message"]["chat"]["id"])
        callback_user_id = str(cq.get("from", {}).get("id", ""))
        
        await self.manager.messaging.answer_callback(cq_id)
        
        # Authorization check
        if not self._is_authorized(chat_id, callback_user_id):
            logger.warning("Unauthorized callback from %s", callback_user_id)
            return
            
        # Route based on callback data prefix
        if data.startswith("wa_"):
            await self._handle_whatsapp_callback(chat_id, data)
        elif data.startswith("exec_"):
            await self._handle_exec_approval_callback(chat_id, data, cq)
        elif data in {"confirm_shutdown", "cancel_shutdown"}:
            await self._handle_shutdown_callback(chat_id, data)
        else:
            logger.warning("Unknown callback data: %s", data)
            
    def _is_authorized(self, chat_id: str, user_id: str) -> bool:
        """Check if callback is from authorized user."""
        if not self.manager.chat_id or chat_id != self.manager.chat_id:
            return False
        # Private chat: must be from the paired user
        if not self.manager.chat_id.startswith("-"):
            return user_id == self.manager.chat_id
        return True
        
    async def _handle_whatsapp_callback(self, chat_id: str, data: str) -> None:
        """Route WhatsApp-related callbacks."""
        if data.startswith("wa_gemini_"):
            await self.manager.whatsapp.handle_gemini_callback(
                chat_id, data[len("wa_gemini_"):]
            )
        elif data.startswith("wa_send_draft_"):
            await self.manager.whatsapp.handle_send_draft_callback(
                chat_id, data[len("wa_send_draft_"):]
            )
        # ... other WA callbacks
        
    async def _handle_exec_approval_callback(
        self, chat_id: str, data: str, cq: dict
    ) -> None:
        """Handle tool execution approval."""
        # Implementation
        
    async def _handle_shutdown_callback(self, chat_id: str, data: str) -> None:
        """Handle dangerous command confirmation."""
        # Implementation
```

**Lines:** ~150-180

---

### 7. `handlers/command_handler.py` - Static Commands

**Purpose:** Handle static bot commands (/start, /help, /status, etc.).

**Contents:**
- `handle_static_command()` - Dispatcher
- `_send_help()` - Help text
- `_send_status()` - System status
- `_send_wa_link_guide()` - WhatsApp linking guide
- `_lock_microphone()` / `_unlock_microphone()` - Mic controls
- `_emergency_stop()` - Stop current task
- `_unpair()` - Unpair bot

**Example:**
```python
"""Static command handlers."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..manager import TelegramBotManager

logger = logging.getLogger(__name__)

class CommandHandler:
    """Handles static bot commands."""
    
    def __init__(self, manager: 'TelegramBotManager'):
        self.manager = manager
        
    async def handle_static_command(
        self, chat_id: str, text_lower: str
    ) -> bool:
        """Handle static commands. Returns True if handled."""
        if text_lower in {"/start", "/help", "❓ help & guide"}:
            await self.send_help(chat_id)
            return True
        elif text_lower in {"/reset", "👤 unpair bot"}:
            await self.unpair(chat_id)
            return True
        elif text_lower in {"/status", "📊 check status"}:
            await self.send_status(chat_id)
            return True
        elif text_lower in {"/screenshot", "📸 get screenshot"}:
            await self.send_screenshot(chat_id)
            return True
        elif text_lower in {"/whatsapp_qr", "🟢 whatsapp qr", "🔑 whatsapp link"}:
            await self.send_wa_link_guide(chat_id)
            return True
        elif text_lower in {"/lock", "🔒 mic lock", "lock mic"}:
            await self.lock_microphone(chat_id)
            return True
        elif text_lower in {"/unlock", "🔓 mic unlock", "unlock mic"}:
            await self.unlock_microphone(chat_id)
            return True
        return False
        
    async def send_help(self, chat_id: str) -> None:
        """Send help message."""
        help_text = """
🤖 *Maya AI - Telegram Interface*

*Basic Commands:*
/start - Show this help
/status - System status
/screenshot - Get desktop screenshot

*Controls:*
🔒 Mic Lock - Pause voice assistant
🔓 Mic Unlock - Resume voice assistant
🛑 Emergency Stop - Cancel current task

*WhatsApp Bridge:*
/whatsapp_qr - Setup WhatsApp integration
"""
        await self.manager.messaging.send_message(
            chat_id, help_text, parse_mode="Markdown"
        )
        
    async def send_status(self, chat_id: str) -> None:
        """Send system status."""
        # Implementation
        
    async def send_wa_link_guide(self, chat_id: str) -> None:
        """Send WhatsApp linking instructions."""
        # Implementation
        
    async def emergency_stop(self, chat_id: str) -> None:
        """Stop current task."""
        task = self.manager._active_tasks.get(chat_id)
        if task and not task.done():
            task.cancel()
            await self.manager.messaging.send_message(
                chat_id,
                "🛑 *Task cancelled.*",
                parse_mode="Markdown"
            )
        else:
            await self.manager.messaging.send_message(
                chat_id,
                "No active task to stop."
            )
            
    async def lock_microphone(self, chat_id: str) -> None:
        """Lock microphone (sleep mode)."""
        # Implementation with process_manager
        
    async def unlock_microphone(self, chat_id: str) -> None:
        """Unlock microphone."""
        # Implementation with process_manager
        
    async def unpair(self, chat_id: str) -> None:
        """Unpair Telegram bot."""
        # Implementation - clear config, reset state
```

**Lines:** ~180-220

---

### 8. `handlers/task_handler.py` - Task Orchestration

**Purpose:** Handle brain orchestrator integration and streaming responses.

**Contents:**
- `_process_and_reply()` - Main orchestrator call
- Streaming logic with live edits
- Task backgrounding after timeout
- Progress callback handling
- Session hooks integration

**Example:**
```python
"""Task processing and orchestrator integration."""

import asyncio
import time
import logging
from typing import TYPE_CHECKING, Optional

from ..config import EDIT_INTERVAL, STREAM_TIMEOUT, BACKGROUND_TASK_TIMEOUT
from ..core.state_models import TelegramTaskState

if TYPE_CHECKING:
    from ..manager import TelegramBotManager

logger = logging.getLogger(__name__)

class TaskHandler:
    """Handles brain orchestrator tasks."""
    
    def __init__(self, manager: 'TelegramBotManager'):
        self.manager = manager
        
    async def process_and_reply(
        self, chat_id: str, text: str, session_id: str
    ) -> None:
        """Process message through orchestrator and stream response."""
        full_response = ""
        sent_msg_id: Optional[str] = None
        current_shown = ""
        last_edit_time = 0.0
        
        task_state = self.manager._task_states.get(chat_id)
        if task_state is None or task_state.session_id != session_id:
            task_state = TelegramTaskState(
                original_text=text,
                session_id=session_id
            )
            self.manager._task_states[chat_id] = task_state
            
        async def _flush(*, final: bool = False) -> None:
            """Flush response to Telegram."""
            nonlocal sent_msg_id, current_shown, last_edit_time
            display = full_response.strip()
            if not display or display == current_shown:
                return
            now = time.monotonic()
            if not final and (now - last_edit_time) < EDIT_INTERVAL:
                return
            last_edit_time = now
            current_shown = display
            suffix = "" if final else " ✍️"
            parse = "Markdown" if final else None
            
            if sent_msg_id is None:
                sent_msg_id = await self.manager.messaging.send_message_get_id(
                    chat_id, display + suffix, parse_mode=parse
                )
            else:
                await self.manager.messaging.edit_message(
                    chat_id, sent_msg_id, display + suffix, parse_mode=parse
                )
                
        try:
            # Suppress voice listener
            suppressed_listener = await self._suppress_voice_listener()
            
            # Create orchestrator turn
            turn_task = asyncio.create_task(
                self._run_orchestrator_turn(
                    chat_id, text, session_id,
                    lambda chunk: self._handle_stream_chunk(chunk, full_response),
                    lambda status: self._handle_progress_update(
                        task_state, status
                    )
                )
            )
            
            # Stream with timeout
            try:
                async with asyncio.timeout(STREAM_TIMEOUT):
                    while not turn_task.done():
                        await asyncio.sleep(0.3)
                        await _flush()
            except asyncio.TimeoutError:
                # Background the task
                task_state.backgrounded = True
                await self.manager.messaging.send_message(
                    chat_id,
                    "Task cholche background-e. Complete hole notify korbo."
                )
                
            # Wait for completion (with hard timeout)
            try:
                async with asyncio.timeout(BACKGROUND_TASK_TIMEOUT):
                    await turn_task
            except asyncio.TimeoutError:
                turn_task.cancel()
                task_state.state = "timed_out"
                
            # Final flush
            await _flush(final=True)
            task_state.state = "completed"
            
        except Exception as exc:
            logger.error("Task error: %s", exc, exc_info=True)
            task_state.state = "failed"
            task_state.error = str(exc)
        finally:
            if suppressed_listener:
                await self._restore_voice_listener(suppressed_listener)
                
    async def _run_orchestrator_turn(
        self, chat_id: str, text: str, session_id: str,
        on_chunk, on_progress
    ):
        """Run brain orchestrator."""
        # Implementation - call brain.orchestrator.run_turn
        pass
        
    def _handle_stream_chunk(self, chunk: dict, full_response: str) -> None:
        """Handle streaming chunk."""
        # Implementation
        pass
        
    def _handle_progress_update(
        self, task_state: TelegramTaskState, status: dict
    ) -> None:
        """Handle progress callback."""
        task_state.updated_at = time.monotonic()
        task_state.active_agent = status.get("agent", "")
        task_state.status = status.get("status", "")
```

**Lines:** ~200-250

---

### 9. `messaging/sender.py` - Message Sending

**Purpose:** Send messages to Telegram API.

**Contents:**
- `_send_message()` - Send text message
- `_send_message_get_id()` - Send and return message ID
- Markdown fallback on error
- Reply markup support

**Example:**
```python
"""Message sending functionality."""

import logging
from typing import TYPE_CHECKING, Optional

from .rate_limiter import RateLimiter

if TYPE_CHECKING:
    from ..manager import TelegramBotManager

logger = logging.getLogger(__name__)

class MessageSender:
    """Handles sending messages to Telegram."""
    
    def __init__(self, manager: 'TelegramBotManager'):
        self.manager = manager
        self.rate_limiter = RateLimiter(manager)
        
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None
    ) -> bool:
        """Send a message. Returns True on success."""
        payload = {
            "chat_id": chat_id,
            "text": text[:4096],  # Telegram limit
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        success = await self.rate_limiter.post_with_retry(
            "sendMessage", payload
        )
        
        # Fallback to plain text if Markdown fails
        if not success and parse_mode == "Markdown":
            logger.warning("Markdown failed, retrying as plain text")
            payload["parse_mode"] = None
            success = await self.rate_limiter.post_with_retry(
                "sendMessage", payload
            )
            
        return success
        
    async def send_message_get_id(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None
    ) -> Optional[str]:
        """Send message and return message ID."""
        payload = {
            "chat_id": chat_id,
            "text": text[:4096],
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        result = await self.rate_limiter.post_with_retry_get_result(
            "sendMessage", payload
        )
        
        if result and "message_id" in result:
            return str(result["message_id"])
            
        # Fallback
        if parse_mode == "Markdown":
            payload["parse_mode"] = None
            result = await self.rate_limiter.post_with_retry_get_result(
                "sendMessage", payload
            )
            if result and "message_id" in result:
                return str(result["message_id"])
                
        return None
```

**Lines:** ~120-150

---

### 10. `messaging/rate_limiter.py` - API Rate Limiting

**Purpose:** Handle Telegram API rate limits with retry and backoff.

**Contents:**
- `_post_with_retry()` - POST with exponential backoff
- Handle 429 rate limit responses
- Automatic retry logic

**Example:**
```python
"""Telegram API rate limiting and retry logic."""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from ..config import TELEGRAM_API, MAX_EDIT_RETRIES

if TYPE_CHECKING:
    from ..manager import TelegramBotManager

logger = logging.getLogger(__name__)

class RateLimiter:
    """Handles API rate limiting."""
    
    def __init__(self, manager: 'TelegramBotManager'):
        self.manager = manager
        
    async def post_with_retry(
        self,
        method: str,
        payload: dict,
        max_retries: int = MAX_EDIT_RETRIES
    ) -> bool:
        """POST with exponential backoff on rate limit."""
        if not self.manager._http or not self.manager.bot_token:
            return False
            
        url = TELEGRAM_API.format(
            token=self.manager.bot_token,
            method=method
        )
        
        retry_delay = 1.0
        for attempt in range(max_retries):
            try:
                resp = await self.manager._http.post(url, json=payload)
                
                if resp.status_code == 200:
                    return True
                elif resp.status_code == 429:
                    # Rate limited
                    retry_after = resp.json().get("parameters", {}).get(
                        "retry_after", retry_delay
                    )
                    logger.warning(
                        "Telegram 429 rate limit, retry after %.1fs",
                        retry_after
                    )
                    await asyncio.sleep(retry_after)
                    retry_delay = retry_after * 2
                else:
                    logger.warning(
                        "Telegram API %s returned %s",
                        method, resp.status_code
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        return False
                        
            except Exception as exc:
                logger.error("API call failed: %s", exc)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    return False
                    
        return False
        
    async def post_with_retry_get_result(
        self,
        method: str,
        payload: dict,
        max_retries: int = MAX_EDIT_RETRIES
    ) -> Optional[dict]:
        """POST with retry, return result on success."""
        # Similar to above but returns JSON result
        pass
```

**Lines:** ~120-150

---

### 11. `whatsapp/notification.py` - WhatsApp Integration

**Purpose:** Handle incoming WhatsApp messages.

**Contents:**
- `_handle_whatsapp_incoming()` - Main entry point
- `_build_wa_notification()` - Build notification markup
- Authorization checks

**Example:**
```python
"""WhatsApp incoming message handling."""

import logging
from typing import TYPE_CHECKING

from ..core.state_models import PendingWAReply
from .ui_copy import get_wa_ui_copy

if TYPE_CHECKING:
    from ..manager import TelegramBotManager

logger = logging.getLogger(__name__)

class WhatsAppNotification:
    """Handles incoming WhatsApp notifications."""
    
    def __init__(self, manager: 'TelegramBotManager'):
        self.manager = manager
        
    async def handle_incoming(self, msg_data: dict) -> None:
        """Handle incoming WhatsApp message."""
        if not self.manager.chat_id:
            logger.warning("No paired Telegram chat for WA message")
            return
            
        # Extract message data
        pending_id = msg_data.get("pending_id")
        chat_id_wa = msg_data.get("chat_id_wa")
        from_number = msg_data.get("from_number", "Unknown")
        from_name = msg_data.get("from_name", "Unknown")
        is_group = msg_data.get("is_group", False)
        group_name = msg_data.get("group_name", "")
        trigger_msg = msg_data.get("trigger_msg", "")
        context = msg_data.get("context_messages", [])
        is_known = msg_data.get("is_known_contact", False)
        gemini_draft = msg_data.get("gemini_draft", "")
        
        # Store pending state
        pending = PendingWAReply(
            id=pending_id,
            chat_id_wa=chat_id_wa,
            from_number=from_number,
            from_name=from_name,
            is_group=is_group,
            group_name=group_name,
            trigger_msg=trigger_msg,
            context_messages=context,
            is_known=is_known,
            gemini_draft=gemini_draft
        )
        self.manager._pending_wa[pending_id] = pending
        
        # Build notification
        notification_text, markup = self._build_notification(pending)
        
        # Send to Telegram
        await self.manager.messaging.send_message(
            self.manager.chat_id,
            notification_text,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    def _build_notification(
        self, pending: PendingWAReply
    ) -> tuple[str, dict]:
        """Build notification text and inline keyboard."""
        style = self.manager.state.get_language_style(
            self.manager.chat_id
        )
        copy = get_wa_ui_copy(style)
        
        # Build text
        source = (
            f"*{pending.group_name}* ({pending.from_name})"
            if pending.is_group
            else f"*{pending.from_name}*"
        )
        
        text = f"📱 {copy['new_message']} {source}\n\n"
        text += f"_{pending.trigger_msg}_\n\n"
        
        if pending.gemini_draft:
            text += f"💡 {copy['suggested_reply']}:\n{pending.gemini_draft}\n\n"
            
        text += copy['action_prompt']
        
        # Build inline keyboard
        buttons = []
        if pending.gemini_draft:
            buttons.append([
                {"text": copy['use_ai'], "callback_data": f"wa_gemini_{pending.id}"},
                {"text": copy['send_draft'], "callback_data": f"wa_send_draft_{pending.id}"}
            ])
        buttons.append([
            {"text": copy['manual'], "callback_data": f"wa_manual_{pending.id}"},
            {"text": copy['ignore'], "callback_data": f"wa_ignore_{pending.id}"}
        ])
        
        if not pending.is_known:
            buttons.append([
                {"text": copy['allow'], "callback_data": f"wa_allow_{pending.id}"},
                {"text": copy['block'], "callback_data": f"wa_block_{pending.id}"}
            ])
            
        markup = {"inline_keyboard": buttons}
        return text, markup
```

**Lines:** ~180-220

---

### 12. `whatsapp/callbacks.py` - WhatsApp Callback Handlers

**Purpose:** Handle WhatsApp-related button callbacks.

**Contents:**
- `_wa_cb_gemini()` - Use AI-generated reply
- `_wa_cb_send_draft()` - Send draft directly
- `_wa_cb_manual()` - Start manual reply flow
- `_wa_cb_ignore()` - Ignore message
- `_wa_cb_allow()` - Allow contact
- `_wa_cb_block()` - Block contact

**Lines:** ~200-250 (multiple callback handlers)

---

### 13. `whatsapp/manual_reply.py` - Manual Reply Flow

**Purpose:** Handle manual reply input from user.

**Contents:**
- `_complete_manual_wa_reply()` - Process user's manual reply
- `_manual_timeout_handler()` - Auto-cancel after timeout
- Timer management

**Lines:** ~100-120

---

### 14. `manager.py` - Main Orchestrator

**Purpose:** Central TelegramBotManager class that coordinates all modules.

**Contents:**
- Constructor initializing all sub-managers
- State dictionaries
- Public API (start, stop, restart)
- Delegation to sub-managers

**Example:**
```python
"""Main Telegram bot manager."""

import asyncio
import logging
from typing import Optional, Dict, Set
import httpx

from .config import *
from .core.lifecycle import LifecycleManager
from .core.polling import PollingManager
from .core.state_models import (
    PendingWAReply, PendingDangerousCmd, TelegramTaskState
)
from .handlers.message_handler import MessageHandler
from .handlers.callback_handler import CallbackHandler
from .handlers.command_handler import CommandHandler
from .handlers.task_handler import TaskHandler
from .messaging.sender import MessageSender
from .messaging.editor import MessageEditor
from .messaging.rate_limiter import RateLimiter
from .whatsapp.notification import WhatsAppNotification
from .whatsapp.callbacks import WhatsAppCallbacks
from .whatsapp.pairing import WhatsAppPairing
from .state.task_state import TaskStateManager
from .state.language_style import LanguageStyleManager

logger = logging.getLogger(__name__)

class TelegramBotManager:
    """Main Telegram bot orchestrator."""
    
    def __init__(self):
        # Config
        self.bot_token: Optional[str] = None
        self.chat_id: Optional[str] = None
        self.pairing_code: Optional[str] = None
        self.enabled: bool = False
        self.running: bool = False
        
        # HTTP client
        self._http: Optional[httpx.AsyncClient] = None
        
        # State
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._task_states: Dict[str, TelegramTaskState] = {}
        self._pending_wa: Dict[str, PendingWAReply] = {}
        self._pending_dangerous: Dict[str, PendingDangerousCmd] = {}
        self._pending_exec_approval: Dict[str, str] = {}
        self._wa_manual_awaiting: Dict[str, str] = {}
        self._wa_manual_timers: Dict[str, asyncio.Task] = {}
        self._background_tasks: Set[asyncio.Task] = set()
        
        # Sub-managers
        self.lifecycle = LifecycleManager(self)
        self.polling = PollingManager(self)
        self.messaging = MessageSender(self)
        self.editor = MessageEditor(self)
        self.message_handler = MessageHandler(self)
        self.callback_handler = CallbackHandler(self)
        self.commands = CommandHandler(self)
        self.tasks = TaskHandler(self)
        self.whatsapp = WhatsAppNotification(self)
        self.wa_callbacks = WhatsAppCallbacks(self)
        self.wa_pairing = WhatsAppPairing(self)
        self.state = TaskStateManager(self)
        self.language = LanguageStyleManager(self)
        
    def load_config(self) -> None:
        """Load configuration."""
        self.lifecycle.load_config()
        
    def start(self) -> None:
        """Start the bot."""
        self.lifecycle.start()
        
    async def stop(self) -> None:
        """Stop the bot."""
        await self.lifecycle.stop()
        
    async def restart(self) -> None:
        """Restart the bot."""
        await self.lifecycle.restart()
        
    def _track_background_task(self, task: asyncio.Task) -> asyncio.Task:
        """Track background task."""
        self._background_tasks.add(task)
        task.add_done_callback(lambda t: self._background_tasks.discard(t))
        return task
```

**Lines:** ~150-180

---

## Migration Strategy

### Phase 1: Foundation (P0 - Week 1)

**Goal:** Create directory structure and move core models/config.

**Steps:**

1. **Create directory structure**
   ```bash
   mkdir -p backend/api/telegram/{core,handlers,whatsapp,messaging,state,utils}
   touch backend/api/telegram/__init__.py
   touch backend/api/telegram/{core,handlers,whatsapp,messaging,state,utils}/__init__.py
   ```

2. **Extract config** → `backend/api/telegram/config.py`
   - Copy all constants from top of file
   - Copy `_is_task_status_request()` helper
   - Test: Import in original file, verify no breakage

3. **Extract state models** → `backend/api/telegram/core/state_models.py`
   - Copy 3 dataclasses
   - Update imports in original file
   - Test: Create instances, verify structure

4. **Create initial `__init__.py`**
   ```python
   # backend/api/telegram/__init__.py
   from .telegram_bot import TelegramBotManager
   
   __all__ = ["TelegramBotManager"]
   ```

**Testing:**
- Import test: `from backend.api.telegram import TelegramBotManager`
- Run existing tests: `pytest tests/api/test_telegram_bot.py`

**Rollback:** Delete new directory, revert imports

---

### Phase 2: Messaging Layer (P0 - Week 1-2)

**Goal:** Extract message sending/editing to separate modules.

**Steps:**

1. **Create `messaging/rate_limiter.py`**
   - Extract `_post_with_retry()` method
   - Make it a class: `RateLimiter`
   - Accept manager reference in constructor

2. **Create `messaging/sender.py`**
   - Extract `_send_message()` and `_send_message_get_id()`
   - Create `MessageSender` class
   - Use `RateLimiter` internally

3. **Create `messaging/editor.py`**
   - Extract `_edit_message()`
   - Create `MessageEditor` class

4. **Create `messaging/typing.py`**
   - Extract `_send_typing()` and `_send_screenshot()`

5. **Update `TelegramBotManager`**
   - Add: `self.messaging = MessageSender(self)`
   - Replace all `self._send_message()` with `self.messaging.send_message()`
   - Replace all `self._edit_message()` with `self.messaging.edit_message()`

**Testing:**
- Unit tests for each messaging class
- Integration test: Send actual message via bot
- Verify Markdown fallback works

**Rollback:** Keep old methods as wrappers calling new ones

---

### Phase 3: Handlers (P0 - Week 2-3)

**Goal:** Separate message/callback routing into handler classes.

**Steps:**

1. **Create `handlers/command_handler.py`**
   - Extract all static command methods
   - Create `CommandHandler` class
   - Methods: `send_help()`, `send_status()`, `emergency_stop()`, etc.

2. **Create `handlers/callback_handler.py`**
   - Extract `_handle_callback_query()`
   - Extract `_answer_callback()`
   - Create routing logic for WA callbacks, exec approval

3. **Create `handlers/message_handler.py`**
   - Extract `_handle_message()`
   - Create routing logic using `CommandHandler`
   - Keep orchestrator routing

4. **Create `handlers/task_handler.py`**
   - Extract `_process_and_reply()`
   - Extract streaming logic
   - Extract `_send_task_status()`

5. **Update `TelegramBotManager`**
   ```python
   self.commands = CommandHandler(self)
   self.message_handler = MessageHandler(self)
   self.callback_handler = CallbackHandler(self)
   self.tasks = TaskHandler(self)
   ```

**Testing:**
- Test each command: /help, /status, /screenshot
- Test callback routing with mock buttons
- Test task streaming with mock orchestrator
- Integration test: Full message flow

**Rollback:** Keep old methods as wrappers

---

### Phase 4: WhatsApp Integration (P1 - Week 3-4)

**Goal:** Modularize WhatsApp-specific functionality.

**Steps:**

1. **Create `whatsapp/ui_copy.py`**
   - Extract `_wa_ui_copy()` static method
   - Create `get_wa_ui_copy()` function

2. **Create `whatsapp/notification.py`**
   - Extract `_handle_whatsapp_incoming()`
   - Extract `_build_wa_notification()`
   - Create `WhatsAppNotification` class

3. **Create `whatsapp/callbacks.py`**
   - Extract all `_wa_cb_*()` methods
   - Create `WhatsAppCallbacks` class

4. **Create `whatsapp/pairing.py`**
   - Extract `_handle_wa_pair()`
   - Extract `_is_wa_pair_command()`
   - Create `WhatsAppPairing` class

5. **Create `whatsapp/manual_reply.py`**
   - Extract `_complete_manual_wa_reply()`
   - Extract `_manual_timeout_handler()`
   - Extract `_cancel_manual_timer()`

6. **Create `whatsapp/authorization.py`**
   - Extract `_require_wa_reply_authorization()`
   - Extract `_send_wa_reply()`

**Testing:**
- Mock WhatsApp incoming messages
- Test all callback buttons
- Test manual reply flow with timeout
- Test authorization logic

---

### Phase 5: Lifecycle & Polling (P0 - Week 4)

**Goal:** Extract lifecycle management and polling.

**Steps:**

1. **Create `core/lifecycle.py`**
   - Extract `load_config()`
   - Extract `start()`
   - Extract `stop()`
   - Extract `restart()`
   - Create `LifecycleManager` class

2. **Create `core/polling.py`**
   - Extract `_poll_loop()`
   - Extract `_claim_update()`
   - Create `PollingManager` class

3. **Update `TelegramBotManager`**
   ```python
   self.lifecycle = LifecycleManager(self)
   self.polling = PollingManager(self)
   
   def start(self):
       self.lifecycle.start()
   ```

**Testing:**
- Test config loading
- Test start/stop/restart sequence
- Test polling with mock updates
- Test duplicate update filtering

---

### Phase 6: State Management (P1 - Week 5)

**Goal:** Centralize state management logic.

**Steps:**

1. **Create `state/task_state.py`**
   - Extract task state management
   - Create `TaskStateManager` class
   - Methods: `get_state()`, `update_state()`, `clear_state()`

2. **Create `state/wa_state.py`**
   - Extract WhatsApp pending state management
   - Create `WAStateManager` class

3. **Create `state/language_style.py`**
   - Extract `_remember_chat_language_style()`
   - Extract `_chat_language_style()`
   - Create `LanguageStyleManager` class

**Testing:**
- Test state transitions
- Test state cleanup
- Test language detection

---

### Phase 7: Utilities & Final Cleanup (P2 - Week 5-6)

**Goal:** Move remaining utilities and finalize.

**Steps:**

1. **Create `utils/keyboard.py`**
   - Extract `_default_keyboard()`

2. **Create `utils/detection.py`**
   - Extract `_is_dangerous_shutdown()`
   - Extract `_detect_language_hint()`

3. **Create `utils/process_cleanup.py`**
   - Extract `_clean_duplicate_processes()`

4. **Create `handlers/approval_handler.py`**
   - Extract dangerous command confirmation
   - Extract tool approval logic
   - Methods: `ask_shutdown_confirm()`, `handle_approval()`

5. **Final manager.py cleanup**
   - Remove all extracted methods
   - Keep only delegation logic
   - Add comprehensive docstrings
   - Target: ~150-200 lines

6. **Update imports across codebase**
   - Update all files importing `telegram_bot`
   - Change to: `from backend.api.telegram import TelegramBotManager`

**Testing:**
- Full integration test suite
- Test all commands end-to-end
- Test WhatsApp flow
- Test dangerous command confirmation
- Load testing: Multiple concurrent messages

---

## Backward Compatibility Strategy

### During Migration (Phases 1-7)

**Dual Implementation:**
```python
# In TelegramBotManager
class TelegramBotManager:
    def __init__(self):
        self.messaging = MessageSender(self)  # New
        
    def _send_message(self, *args, **kwargs):
        """Deprecated: Use self.messaging.send_message()"""
        return self.messaging.send_message(*args, **kwargs)
```

**Benefits:**
- Existing code continues working
- Gradual migration of callsites
- Easy rollback if issues found

### After Migration Complete

**Deprecation notices:**
```python
@deprecated("Use self.messaging.send_message() instead")
def _send_message(self, *args, **kwargs):
    return self.messaging.send_message(*args, **kwargs)
```

**Final cleanup** (Week 7):
- Remove all deprecated wrappers
- Update documentation
- Final test pass

---

## Import Dependency Graph

```
manager.py (TelegramBotManager)
├── config.py
├── core/
│   ├── state_models.py (no deps)
│   ├── lifecycle.py
│   │   ├── backend.database.*
│   │   └── httpx
│   └── polling.py
│       ├── config.py
│       └── httpx
├── handlers/
│   ├── message_handler.py
│   │   ├── config.py
│   │   ├── commands (CommandHandler)
│   │   ├── tasks (TaskHandler)
│   │   └── whatsapp (WhatsAppPairing)
│   ├── callback_handler.py
│   │   ├── whatsapp.callbacks
│   │   └── messaging.sender
│   ├── command_handler.py
│   │   ├── messaging.sender
│   │   └── backend.system.process_manager
│   ├── task_handler.py
│   │   ├── config.py
│   │   ├── core.state_models
│   │   ├── messaging.*
│   │   └── backend.brain.orchestrator
│   └── approval_handler.py
│       ├── config.py
│       ├── messaging.sender
│       └── backend.brain.reasoning.tool_planner
├── whatsapp/
│   ├── ui_copy.py (no deps)
│   ├── notification.py
│   │   ├── core.state_models
│   │   ├── ui_copy
│   │   └── messaging.sender
│   ├── callbacks.py
│   │   ├── core.state_models
│   │   ├── authorization
│   │   └── messaging.*
│   ├── pairing.py
│   │   ├── messaging.sender
│   │   └── backend.database.*
│   ├── manual_reply.py
│   │   ├── core.state_models
│   │   ├── authorization
│   │   └── messaging.sender
│   └── authorization.py
│       └── backend.whatsapp.manager (external)
├── messaging/
│   ├── rate_limiter.py
│   │   ├── config.py
│   │   └── httpx
│   ├── sender.py
│   │   ├── rate_limiter
│   │   └── config.py
│   ├── editor.py
│   │   ├── rate_limiter
│   │   └── config.py
│   └── typing.py
│       ├── sender
│       ├── backend.vision.capture.screen_capture
│       └── httpx
├── state/
│   ├── task_state.py
│   │   └── core.state_models
│   ├── wa_state.py
│   │   └── core.state_models
│   └── language_style.py
│       └── backend.brain.language_style
└── utils/
    ├── keyboard.py (no deps)
    ├── detection.py
    │   └── config.py
    └── process_cleanup.py
        └── subprocess
```

**Key Observations:**
- `config.py` and `core/state_models.py` have no internal deps (foundation)
- `messaging/` layer is self-contained
- `handlers/` depend on messaging and whatsapp
- Clean separation: no circular dependencies

---

## Code Examples: Before & After

### Example 1: Sending a Message

**Before (2000-line file):**
```python
# In TelegramBotManager class, line 1953
async def _send_message(
    self,
    chat_id: str,
    text: str,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[dict] = None
) -> bool:
    # ... 50 lines of implementation
    pass

# Usage (line 450)
await self._send_message(chat_id, "Hello")
```

**After (modular):**
```python
# backend/api/telegram/messaging/sender.py (~150 lines)
class MessageSender:
    async def send_message(
        self, chat_id: str, text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None
    ) -> bool:
        # Implementation here
        pass

# backend/api/telegram/manager.py (line 30)
self.messaging = MessageSender(self)

# Usage (line 120)
await self.messaging.send_message(chat_id, "Hello")
```

**Benefits:**
- `MessageSender` can be tested independently
- Clear responsibility: only handles sending
- Easy to mock in tests

---

### Example 2: WhatsApp Callbacks

**Before:**
```python
# Lines 1283-1563 in one class
async def _wa_cb_gemini(self, chat_id: str, pending_id: str):
    # ... 70 lines
    
async def _wa_cb_send_draft(self, chat_id: str, pending_id: str):
    # ... 20 lines
    
async def _wa_cb_manual(self, chat_id: str, pending_id: str):
    # ... 25 lines
    
# ... 6 more callback methods
```

**After:**
```python
# backend/api/telegram/whatsapp/callbacks.py (~250 lines)
class WhatsAppCallbacks:
    def __init__(self, manager):
        self.manager = manager
        
    async def handle_gemini(self, chat_id: str, pending_id: str):
        # Implementation
        
    async def handle_send_draft(self, chat_id: str, pending_id: str):
        # Implementation
        
    # ... all WA callbacks grouped together

# backend/api/telegram/handlers/callback_handler.py
async def _handle_whatsapp_callback(self, chat_id: str, data: str):
    if data.startswith("wa_gemini_"):
        await self.manager.wa_callbacks.handle_gemini(
            chat_id, data[len("wa_gemini_"):]
        )
    # ... other routes
```

**Benefits:**
- All WhatsApp logic in one module
- Easy to understand WhatsApp integration
- Can be tested without full bot setup

---

### Example 3: Manager Class Simplification

**Before (manager.py - 2000 lines):**
```python
class TelegramBotManager:
    def __init__(self):
        # 30+ instance variables
        self.bot_token = None
        self.chat_id = None
        self._http = None
        self._active_tasks = {}
        self._task_states = {}
        self._pending_wa = {}
        # ... 25 more
        
    # 50+ methods all in one class
    async def _handle_message(self, msg): pass
    async def _handle_callback_query(self, cq): pass
    async def _send_message(self, ...): pass
    async def _edit_message(self, ...): pass
    async def _wa_cb_gemini(self, ...): pass
    # ... 45 more methods
```

**After (manager.py - ~180 lines):**
```python
class TelegramBotManager:
    """Central orchestrator - delegates to specialized managers."""
    
    def __init__(self):
        # Core config (only 5-6 variables)
        self.bot_token: Optional[str] = None
        self.chat_id: Optional[str] = None
        self.enabled: bool = False
        self.running: bool = False
        self._http: Optional[httpx.AsyncClient] = None
        
        # State (managed by sub-managers)
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._task_states: Dict[str, TelegramTaskState] = {}
        self._pending_wa: Dict[str, PendingWAReply] = {}
        # ... (kept for backward compat, will migrate to state managers)
        
        # Specialized managers (delegation pattern)
        self.lifecycle = LifecycleManager(self)
        self.polling = PollingManager(self)
        self.messaging = MessageSender(self)
        self.editor = MessageEditor(self)
        self.message_handler = MessageHandler(self)
        self.callback_handler = CallbackHandler(self)
        self.commands = CommandHandler(self)
        self.tasks = TaskHandler(self)
        self.whatsapp = WhatsAppNotification(self)
        self.wa_callbacks = WhatsAppCallbacks(self)
        self.state = TaskStateManager(self)
        
    # Public API (delegation)
    def load_config(self) -> None:
        self.lifecycle.load_config()
        
    def start(self) -> None:
        self.lifecycle.start()
        
    async def stop(self) -> None:
        await self.lifecycle.stop()
        
    # Internal delegation (during migration)
    async def _handle_message(self, msg: dict) -> None:
        await self.message_handler.handle_message(msg)
        
    async def _handle_callback_query(self, cq: dict) -> None:
        await self.callback_handler.handle_callback_query(cq)
```

**Benefits:**
- Manager is now a coordinator, not a monolith
- Each concern has its own file
- Easy to understand the overall architecture
- Clear delegation pattern

---

## Testing Strategy

### Unit Tests (Per Module)

**1. Messaging Tests** (`tests/api/telegram/test_messaging.py`)
```python
import pytest
from backend.api.telegram.messaging.sender import MessageSender
from backend.api.telegram.messaging.rate_limiter import RateLimiter

@pytest.mark.asyncio
async def test_send_message_success(mock_manager, mock_http_client):
    """Test successful message send."""
    sender = MessageSender(mock_manager)
    mock_manager._http = mock_http_client
    
    result = await sender.send_message("12345", "Test message")
    assert result is True
    
@pytest.mark.asyncio
async def test_send_message_markdown_fallback(mock_manager):
    """Test Markdown fallback on error."""
    sender = MessageSender(mock_manager)
    # Mock 400 error on Markdown, success on plain
    result = await sender.send_message(
        "12345", "Test *markdown*", parse_mode="Markdown"
    )
    assert result is True  # Should fallback to plain text
    
@pytest.mark.asyncio
async def test_rate_limiter_429_backoff(mock_manager):
    """Test exponential backoff on 429 rate limit."""
    limiter = RateLimiter(mock_manager)
    # Mock 429 response with retry_after
    # Verify it waits and retries
```

**2. Handler Tests** (`tests/api/telegram/test_handlers.py`)
```python
@pytest.mark.asyncio
async def test_message_handler_routes_static_commands(mock_manager):
    """Test static command routing."""
    handler = MessageHandler(mock_manager)
    mock_manager.chat_id = "12345"
    
    msg = {"chat": {"id": "12345"}, "text": "/help"}
    await handler.handle_message(msg)
    
    # Verify CommandHandler.send_help was called
    assert mock_manager.commands.send_help.called
    
@pytest.mark.asyncio
async def test_callback_handler_authorization(mock_manager):
    """Test unauthorized callback rejection."""
    handler = CallbackHandler(mock_manager)
    mock_manager.chat_id = "12345"
    
    cq = {
        "id": "1",
        "data": "wa_gemini_abc",
        "message": {"chat": {"id": "67890"}},  # Wrong chat
        "from": {"id": "67890"}
    }
    await handler.handle_callback_query(cq)
    
    # Verify no action taken
    assert not mock_manager.wa_callbacks.handle_gemini.called
```

**3. WhatsApp Tests** (`tests/api/telegram/test_whatsapp.py`)
```python
@pytest.mark.asyncio
async def test_wa_notification_builds_correctly(mock_manager):
    """Test WhatsApp notification markup."""
    notifier = WhatsAppNotification(mock_manager)
    
    msg_data = {
        "pending_id": "abc123",
        "chat_id_wa": "wa_chat",
        "from_number": "+1234567890",
        "from_name": "John Doe",
        "is_group": False,
        "trigger_msg": "Hello",
        "is_known_contact": True,
        "gemini_draft": "Hi there!"
    }
    
    await notifier.handle_incoming(msg_data)
    
    # Verify notification sent
    assert mock_manager.messaging.send_message.called
    call_args = mock_manager.messaging.send_message.call_args
    assert "John Doe" in call_args[0][1]  # Text contains name
    assert "inline_keyboard" in call_args[1]["reply_markup"]
```

---

### Integration Tests

**Full Flow Test** (`tests/api/telegram/test_integration.py`)
```python
@pytest.mark.asyncio
async def test_full_message_to_response_flow(telegram_bot_manager):
    """Test complete message handling flow."""
    # Setup
    bot = telegram_bot_manager
    bot.load_config()
    bot.start()
    
    # Simulate incoming message
    msg = {
        "update_id": 1,
        "message": {
            "chat": {"id": bot.chat_id},
            "text": "/help"
        }
    }
    
    await bot.message_handler.handle_message(msg["message"])
    
    # Verify response sent (mock Telegram API)
    # Check that help message was sent
    
    await bot.stop()
```

**WhatsApp Integration Test**
```python
@pytest.mark.asyncio
async def test_wa_manual_reply_flow(telegram_bot_manager):
    """Test manual WhatsApp reply flow."""
    bot = telegram_bot_manager
    
    # 1. Incoming WA message
    wa_msg = {"pending_id": "test123", ...}
    await bot.whatsapp.handle_incoming(wa_msg)
    
    # 2. User clicks "Manual Reply"
    cq = {"id": "1", "data": "wa_manual_test123", ...}
    await bot.callback_handler.handle_callback_query(cq)
    
    # 3. User types reply
    reply_msg = {"chat": {"id": bot.chat_id}, "text": "My reply"}
    await bot.message_handler.handle_message(reply_msg)
    
    # Verify reply sent to WhatsApp
    # Check timer cancelled
```

---

## Benefits Summary

### Code Quality Improvements

**1. File Size Reduction**
- Before: 1 file × 2000 lines = 2000 lines
- After: 15-20 files × 100-200 lines = ~2500 lines total
- *Note: Slight increase due to class structure overhead, but massive readability gain*

**2. Single Responsibility Principle**
- Each module has one clear purpose
- Easy to understand what each file does
- Changes are localized to specific modules

**3. Testability**
- Unit tests for each module
- Easy to mock dependencies
- Faster test execution (parallel tests)

**4. Maintainability**
- Bug fixes: know exactly which file to modify
- New features: clear where to add code
- Code review: smaller, focused diffs

**5. Onboarding**
- New developers can understand one module at a time
- Clear architecture overview
- Self-documenting structure

### Performance Improvements

**No Negative Impact:**
- Python imports are cached
- Object instantiation overhead is negligible
- All async behavior unchanged

**Potential Gains:**
- Parallel testing (CI speedup)
- Better code splitting for hot-reloading (dev experience)

---

## Risk Mitigation

### Potential Risks & Mitigations

**Risk 1: Breaking Changes During Migration**
- **Mitigation:** Dual implementation (old + new) during transition
- **Rollback:** Keep old methods as wrappers until fully tested

**Risk 2: Import Circular Dependencies**
- **Mitigation:** Follow dependency graph (config → models → messaging → handlers)
- **Detection:** Run `pylint` with circular dependency checks

**Risk 3: Lost Functionality**
- **Mitigation:** Comprehensive test suite before starting
- **Verification:** Integration tests after each phase

**Risk 4: Performance Regression**
- **Mitigation:** Benchmark critical paths (message latency)
- **Monitoring:** Add timing logs during migration

**Risk 5: Git Merge Conflicts (if others working on file)**
- **Mitigation:** Coordinate with team, do refactoring in dedicated branch
- **Strategy:** Frequent small merges, not one big bang

---

## Success Metrics

### Quantitative Metrics

**Before Refactoring:**
- Largest file: 2000 lines
- Number of classes in one file: 4
- Number of methods in main class: 50+
- Average method length: 30-50 lines
- Test coverage: ~60% (estimated)
- Time to understand codebase: 4-6 hours

**After Refactoring (Target):**
- Largest file: <250 lines
- Number of modules: 15-20
- Average file size: 120-180 lines
- Average method length: 10-20 lines
- Test coverage: >80%
- Time to understand codebase: 2-3 hours (clear structure)

### Qualitative Goals

- [ ] New developer can find where to add a command in <5 minutes
- [ ] Bug in messaging logic can be fixed without touching handlers
- [ ] WhatsApp integration can be understood independently
- [ ] Unit tests run in <10 seconds (parallelized)
- [ ] Code review diffs are <200 lines per feature

---

## Timeline Summary

| Phase | Duration | Priority | Deliverables |
|-------|----------|----------|-------------|
| 1. Foundation | Week 1 | P0 | config.py, state_models.py, directory structure |
| 2. Messaging | Week 1-2 | P0 | sender.py, editor.py, rate_limiter.py, typing.py |
| 3. Handlers | Week 2-3 | P0 | message_handler.py, callback_handler.py, command_handler.py, task_handler.py |
| 4. WhatsApp | Week 3-4 | P1 | notification.py, callbacks.py, pairing.py, manual_reply.py |
| 5. Lifecycle | Week 4 | P0 | lifecycle.py, polling.py |
| 6. State | Week 5 | P1 | task_state.py, wa_state.py, language_style.py |
| 7. Utilities | Week 5-6 | P2 | keyboard.py, detection.py, approval_handler.py |
| 8. Final Cleanup | Week 6-7 | P0 | Remove deprecated code, documentation, final tests |

**Total Duration:** 6-7 weeks (with 1 developer full-time)

**Parallel Work Possible:**
- Phases 2 & 3 can partially overlap (messaging → handlers)
- Phases 4 & 6 can be done in parallel (WhatsApp & State)

---

## Quick Start Guide (For Implementation)

### Step-by-Step First Actions

**Day 1: Setup**
```bash
# 1. Create branch
git checkout -b refactor/telegram-bot-modular

# 2. Create directory structure
mkdir -p backend/api/telegram/{core,handlers,whatsapp,messaging,state,utils}

# 3. Create __init__.py files
touch backend/api/telegram/__init__.py
find backend/api/telegram -type d -exec touch {}/__init__.py \;

# 4. Run tests (baseline)
pytest tests/api/test_telegram_bot.py -v
```

**Day 2-3: Extract Config & Models**
```bash
# 1. Create config.py
code backend/api/telegram/config.py
# Copy constants from telegram_bot.py lines 60-105

# 2. Create state_models.py
code backend/api/telegram/core/state_models.py
# Copy 3 dataclasses from lines 116-150

# 3. Update imports in telegram_bot.py
# Add: from backend.api.telegram.config import *
# Add: from backend.api.telegram.core.state_models import *

# 4. Test
pytest tests/api/test_telegram_bot.py -v
# Should pass with no changes
```

**Week 1: Messaging Layer**
```python
# 1. Create rate_limiter.py
# Extract _post_with_retry method → RateLimiter class

# 2. Create sender.py
# Extract _send_message* methods → MessageSender class

# 3. Update TelegramBotManager.__init__
self.messaging = MessageSender(self)

# 4. Create wrapper (backward compat)
async def _send_message(self, *args, **kwargs):
    return await self.messaging.send_message(*args, **kwargs)

# 5. Test each module
pytest tests/api/telegram/test_messaging.py -v
```

**Progress Tracking:**
```bash
# Check file sizes
wc -l backend/api/telegram/**/*.py

# Check test coverage
pytest --cov=backend.api.telegram --cov-report=html

# Verify no circular imports
pydeps backend/api/telegram --show-deps
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Circular Imports
**Problem:** `manager.py` imports `handlers`, handlers import `manager`

**Solution:** Use `TYPE_CHECKING` for type hints
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..manager import TelegramBotManager

class MessageHandler:
    def __init__(self, manager: 'TelegramBotManager'):
        self.manager = manager
```

### Pitfall 2: Shared State Access
**Problem:** Multiple modules need `_active_tasks` dict

**Solution:** Keep state in manager, access via reference
```python
# In MessageHandler
def some_method(self):
    task = self.manager._active_tasks.get(chat_id)  # Access via manager
```

### Pitfall 3: Async Context Issues
**Problem:** Cannot call `async` methods from `__init__`

**Solution:** Use `start()` method for async initialization
```python
class LifecycleManager:
    def __init__(self, manager):
        self.manager = manager
        self.http_client = None  # Not initialized yet
        
    def start(self):
        """Called from async context."""
        self.http_client = httpx.AsyncClient(...)
```

---

## Future Enhancements (Post-Refactoring)

Once the modular structure is in place, these improvements become easier:

### 1. Plugin System for Commands
```python
# backend/api/telegram/plugins/weather.py
class WeatherCommand:
    command = "/weather"
    
    async def handle(self, chat_id: str, args: str):
        # Implementation
        
# Auto-discover and register plugins
```

### 2. Middleware Pipeline
```python
# backend/api/telegram/middleware/
# - logging_middleware.py
# - rate_limiting_middleware.py
# - analytics_middleware.py

class MessagePipeline:
    def __init__(self):
        self.middlewares = [
            LoggingMiddleware(),
            RateLimitingMiddleware(),
            AnalyticsMiddleware()
        ]
```

### 3. Event-Driven Architecture
```python
# backend/api/telegram/events/
# Instead of direct calls, emit events

await self.events.emit("message_received", msg)
await self.events.emit("task_completed", result)

# Subscribers in different modules
@on_event("task_completed")
async def notify_user(result):
    # Send notification
```

### 4. Dependency Injection
```python
# Instead of passing manager reference everywhere
class MessageHandler:
    def __init__(
        self,
        messaging: MessageSender,
        commands: CommandHandler,
        config: Config
    ):
        self.messaging = messaging
        self.commands = commands
        self.config = config
```

### 5. Async Queues for Scalability
```python
# backend/api/telegram/queues/
# Separate message ingestion from processing

class MessageQueue:
    async def enqueue(self, msg: dict):
        await self.queue.put(msg)
        
    async def process_loop(self):
        while True:
            msg = await self.queue.get()
            await self.handler.handle(msg)
```

---

## Documentation Updates Needed

### 1. Architecture Diagram
```
docs/telegram_bot_architecture.md
- Component diagram
- Data flow diagram
- State machine diagram (task lifecycle)
```

### 2. Developer Guide
```
docs/telegram_bot_development.md
- How to add a new command
- How to add a WhatsApp callback
- How to test your changes
- Common debugging scenarios
```

### 3. API Reference
```
docs/telegram_bot_api.md
- TelegramBotManager public API
- Each sub-manager's public methods
- Configuration options
- Event hooks
```

---

## Conclusion

This refactoring plan provides a **structured, incremental approach** to splitting the 2000-line `telegram_bot.py` into **15-20 modular components**. 

**Key Principles:**
1. **Gradual migration** - No big bang, each phase is tested
2. **Backward compatibility** - Old code continues working during transition
3. **Clear ownership** - Each module has one responsibility
4. **Comprehensive testing** - Unit + integration tests at each phase

**Expected Outcomes:**
- ✅ File sizes: 100-200 lines each
- ✅ Test coverage: >80%
- ✅ Developer velocity: 2x faster (easier to understand + modify)
- ✅ Bug density: Lower (isolated concerns, better tests)
- ✅ Maintainability: Significantly improved

**Timeline:** 6-7 weeks with 1 full-time developer

**Next Steps:**
1. Review this plan with the team
2. Create tracking issues for each phase
3. Set up test infrastructure
4. Begin Phase 1: Foundation

---

*Document Version: 1.0*  
*Last Updated: 2025*  
*Author: Maya AI Refactoring Team*
