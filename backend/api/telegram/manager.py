"""
manager.py
==========
Refactored Telegram Bot Manager - Slim orchestrator that delegates to specialized modules.

This manager serves as a thin coordination layer that:
- Initializes all sub-managers and handlers
- Maintains shared state (config, tasks, pending approvals, WhatsApp state)
- Delegates operations to appropriate specialized modules
- Provides backward compatibility wrappers for legacy code

Architecture:
- Core: Lifecycle, Polling
- Messaging: Sender, Editor, TypingIndicator, RateLimiter
- Handlers: MessageHandler, CallbackHandler, CommandHandler
- WhatsApp: WhatsAppNotification
- State: Shared dictionaries for tasks, approvals, manual replies
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import time
from typing import Dict, Optional, Set

import httpx

from backend.brain.language_style import (
    BANGLISH,
    HINDILISH,
    detect_language_style,
    get_latest_conversation_style,
    set_latest_conversation_style,
)

# Import all sub-managers
from backend.api.telegram.core.lifecycle import LifecycleManager
from backend.api.telegram.core.polling import PollingManager
from backend.api.telegram.messaging.sender import MessageSender
from backend.api.telegram.messaging.editor import MessageEditor
from backend.api.telegram.messaging.typing import TypingIndicator
from backend.api.telegram.handlers.message_handler import MessageHandler
from backend.api.telegram.handlers.callback_handler import CallbackHandler
from backend.api.telegram.handlers.command_handler import CommandHandler
from backend.api.telegram.handlers.task_handler import TaskHandler
from backend.api.telegram.whatsapp.notification import WhatsAppNotification
from backend.api.telegram.core.state_models import (
    PendingWAReply,
    PendingDangerousCmd,
    TelegramTaskState,
)

logger = logging.getLogger(__name__)


class TelegramBotManager:
    """
    Slim orchestrator for Telegram bot operations.
    
    This manager delegates most functionality to specialized sub-managers,
    maintaining only shared state and providing a clean public API.
    """

    def __init__(self) -> None:
        """Initialize the manager and all sub-managers."""
        
        # ──────────────────────────────────────────────────────────────────
        # Configuration (loaded by lifecycle.load_config())
        # ──────────────────────────────────────────────────────────────────
        self.bot_token: Optional[str] = None
        self.chat_id: Optional[str] = None
        self.pairing_code: Optional[str] = None
        self.enabled: bool = False

        # ──────────────────────────────────────────────────────────────────
        # Runtime state
        # ──────────────────────────────────────────────────────────────────
        self.running: bool = False
        self._http: Optional[httpx.AsyncClient] = None   # persistent HTTP client

        # ──────────────────────────────────────────────────────────────────
        # Task management
        # ──────────────────────────────────────────────────────────────────
        # Per-chat active task (for emergency stop)
        self._active_tasks: Dict[str, asyncio.Task] = {}
        # Latest task snapshot (backgrounded results remain queryable)
        self._task_states: Dict[str, TelegramTaskState] = {}
        # Track all background tasks to prevent accumulation
        self._background_tasks: Set[asyncio.Task] = set()

        # ──────────────────────────────────────────────────────────────────
        # Approval state
        # ──────────────────────────────────────────────────────────────────
        # Dangerous command confirmations — keyed by telegram_chat_id
        self._pending_dangerous: Dict[str, PendingDangerousCmd] = {}
        # Generic agent-tool approval currently shown in each Telegram chat
        self._pending_exec_approval: Dict[str, str] = {}

        # ──────────────────────────────────────────────────────────────────
        # WhatsApp state
        # ──────────────────────────────────────────────────────────────────
        # WhatsApp incoming — keyed by pending_id
        self._pending_wa: Dict[str, PendingWAReply] = {}
        # Latest conversational style used by each paired Telegram chat
        self._chat_language_styles: Dict[str, str] = {}
        # telegram_chat_id → pending_id (set while waiting for manual reply)
        self._wa_manual_awaiting: Dict[str, str] = {}
        # pending_id → asyncio.Task (auto-cancel timer)
        self._wa_manual_timers: Dict[str, asyncio.Task] = {}

        # ──────────────────────────────────────────────────────────────────
        # Background tasks (managed by lifecycle)
        # ──────────────────────────────────────────────────────────────────
        self._poll_task: Optional[asyncio.Task] = None
        self._wa_listener_task: Optional[asyncio.Task] = None
        self._wa_cleanup_task: Optional[asyncio.Task] = None

        # ──────────────────────────────────────────────────────────────────
        # Sub-managers (delegation targets)
        # ──────────────────────────────────────────────────────────────────
        self.lifecycle = LifecycleManager(self)
        self.polling = PollingManager(self)
        self.message_sender = MessageSender(self)
        self.message_editor = MessageEditor(self)
        self.typing_indicator = TypingIndicator(self)
        self.message_handler = MessageHandler(self)
        self.callback_handler = CallbackHandler(self)
        self.command_handler = CommandHandler(self)
        self.task_handler = TaskHandler(self)
        self.whatsapp = WhatsAppNotification(self)

    # ──────────────────────────────────────────────────────────────────────────
    # Public API (delegates to lifecycle manager)
    # ──────────────────────────────────────────────────────────────────────────

    def load_config(self) -> None:
        """Load/refresh config from database."""
        self.lifecycle.load_config()

    def start(self) -> None:
        """Start the bot (call from asyncio context, after load_config)."""
        self.lifecycle.start()

    async def stop(self) -> None:
        """Gracefully stop all tasks and close HTTP client."""
        await self.lifecycle.stop()

    async def restart(self) -> None:
        """Restart the bot (stop + start)."""
        await self.lifecycle.restart()

    # ──────────────────────────────────────────────────────────────────────────
    # Background task tracking
    # ──────────────────────────────────────────────────────────────────────────

    def _track_background_task(self, task: asyncio.Task) -> asyncio.Task:
        """
        Track a background task and automatically remove it when done.
        
        Args:
            task: The asyncio Task to track
            
        Returns:
            The same task (for chaining)
        """
        self._background_tasks.add(task)
        task.add_done_callback(lambda t: self._background_tasks.discard(t))
        
        # Log any exceptions that occurred in the task
        def _log_exception(t: asyncio.Task) -> None:
            try:
                if not t.cancelled() and t.exception() is not None:
                    logger.error(
                        "Background task %s raised an exception: %s",
                        t.get_name(),
                        t.exception(),
                        exc_info=t.exception()
                    )
            except Exception:
                pass
        task.add_done_callback(_log_exception)
        return task

    # ──────────────────────────────────────────────────────────────────────────
    # Language style management
    # ──────────────────────────────────────────────────────────────────────────

    def _remember_chat_language_style(self, chat_id: str, text: str) -> str:
        """
        Track the paired user's latest Maya conversation style.
        
        Args:
            chat_id: Telegram chat ID
            text: User message text
            
        Returns:
            Detected language style
        """
        style = detect_language_style(
            text,
            fallback=self._chat_language_styles.get(chat_id),
        )
        self._chat_language_styles[chat_id] = style
        set_latest_conversation_style(style)
        return style

    def _chat_language_style(self, chat_id: str) -> str:
        """
        Get the current language style for a chat.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            Language style (BANGLISH, HINDILISH, or ENGLISH)
        """
        return get_latest_conversation_style()

    # ──────────────────────────────────────────────────────────────────────────
    # Backward compatibility properties (for tests and old code)
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def messaging(self):
        """Backward compatibility: messaging → message_sender"""
        return self.message_sender

    @property
    def typing(self):
        """Backward compatibility: typing → typing_indicator"""
        return self.typing_indicator

    @property
    def utils(self):
        """Backward compatibility: utils module stub"""
        class UtilsStub:
            def __init__(self, manager):
                self._manager = manager
            def default_keyboard(self):
                return self._manager._default_keyboard()
        return UtilsStub(self)

    def _build_wa_notification(self, pending, style=None):
        """Backward compatibility: delegate to whatsapp module"""
        return self.whatsapp.build_wa_notification(pending, style or get_latest_conversation_style())

    async def _handle_whatsapp_incoming(self, msg_data: dict) -> None:
        """Backward compatibility: delegate to whatsapp module"""
        await self.whatsapp.handle_whatsapp_incoming(msg_data)

    def _wa_ui_copy(self, style: str) -> dict:
        """Backward compatibility: Get comprehensive UI copy with all keys"""
        return self._get_full_ui_copy(style)

    def wa_ui_copy(self, style: str) -> dict:
        """Public wrapper for _wa_ui_copy"""
        return self._get_full_ui_copy(style)

    def _get_full_ui_copy(self, style: str) -> dict[str, str]:
        """
        Get complete UI copy dictionary with all keys needed by telegram bot.
        Combines WhatsApp notification keys with general bot keys.
        """
        # Get WhatsApp-specific keys
        wa_copy = WhatsAppNotification._wa_ui_copy(style)
        
        # Add general bot keys
        if style == BANGLISH:
            wa_copy.update({
                "approval_received": "✅ Onumodi peyechi. Ekhon execute korchi.",
                "command_cancelled": "❌ Command cancel kora hoyeche.",
                "default_task_done": "✅ Kaj hoye geche.",
                "task_running": "Agger kaj-ta ekhono {location}cholche.\nElapsed: {elapsed}\nCurrent step: {stage}\n\nComplete hole final result automatically pathabo.",
                "task_completed_status": "Agger kaj-ta complete hoyeche ({elapsed}).\nFinal result already pathano hoyeche.",
                "task_timed_out_status": "Agger kaj-ta {elapsed} por hard timeout-e stop hoyeche.\nSame request abar dile Maya notun kore run korbe.",
                "task_failed_status": "Agger kaj-ta fail koreche: {detail}",
                "task_cancelled_status": "Agger kaj-ta cancel hoyeche.",
                "task_hard_timeout": "Kaj-ta maximum background runtime cross koreche, tai stop kora hoyeche. Same request abar dile notun kore run hobe.",
                "pairing_success": "🟢 *Pairing Successful!*\n\nApni ekhon Maya AI-ke Telegram theke command korte parben.",
                "pairing_prompt": "Pair korte pathaan:\n`/pair {code}`",
                "unpaired": "🔴 *Unpaired.*\n\nJekonosamay `/pair [passcode]` diye notun account pair korun.",
                "help_status_line": "📊 *Status:* `/status` check koro",
                "help_screenshot_line": "📸 *Screenshot:* `/screenshot` pathao",
            })
        elif style == HINDILISH:
            wa_copy.update({
                "approval_received": "✅ Anumati mili. Ab execute kar rahi hun.",
                "command_cancelled": "❌ Command cancel kar diya gaya hai.",
                "default_task_done": "✅ Kaam ho gaya.",
                "task_running": "Pehle ka kaam abhi {location}chal raha hai.\nElapsed: {elapsed}\nCurrent step: {stage}\n\nComplete hone par final result automatically bhejungi.",
                "task_completed_status": "Pehle ka kaam complete ho gaya ({elapsed}).\nFinal result already bheja ja chuka hai.",
                "task_timed_out_status": "Pehle ka kaam {elapsed} ke baad hard timeout se stop ho gaya.\nSame request phir se dene par Maya naye sir se chalayegi.",
                "task_failed_status": "Pehle ka kaam fail ho gaya: {detail}",
                "task_cancelled_status": "Pehle ka kaam cancel ho gaya.",
                "task_hard_timeout": "Kaam ne maximum background runtime cross kar liya, isliye stop kiya gaya. Same request phir se dene par naye sir se chalega.",
                "pairing_success": "🟢 *Pairing Successful!*\n\nAap ab Maya AI ko Telegram se command kar sakte hain.",
                "pairing_prompt": "Pair karne ke liye bheje:\n`/pair {code}`",
                "unpaired": "🔴 *Unpaired.*\n\nKabhi bhi `/pair [passcode]` se naya account pair karein.",
                "help_status_line": "📊 *Status:* `/status` check karo",
                "help_screenshot_line": "📸 *Screenshot:* `/screenshot` bhejo",
            })
        else:  # ENGLISH
            wa_copy.update({
                "approval_received": "✅ Approval received. Executing now.",
                "command_cancelled": "❌ Command cancelled.",
                "default_task_done": "✅ Task completed.",
                "task_running": "Previous task is still {location}running.\nElapsed: {elapsed}\nCurrent step: {stage}\n\nWill automatically send the final result once complete.",
                "task_completed_status": "Previous task completed ({elapsed}).\nFinal result has already been sent.",
                "task_timed_out_status": "Previous task stopped after hard timeout at {elapsed}.\nSending the same request again will run it freshly.",
                "task_failed_status": "Previous task failed: {detail}",
                "task_cancelled_status": "Previous task was cancelled.",
                "task_hard_timeout": "Task crossed maximum background runtime and was stopped. Sending the same request again will run it freshly.",
                "pairing_success": "🟢 *Pairing Successful!*\n\nYou can now command Maya AI from Telegram.",
                "pairing_prompt": "To pair, send:\n`/pair {code}`",
                "unpaired": "🔴 *Unpaired.*\n\nYou can pair a new account anytime using `/pair [passcode]`.",
                "help_status_line": "📊 *Status:* Check with `/status`",
                "help_screenshot_line": "📸 *Screenshot:* Send `/screenshot`",
            })
        
        return wa_copy

    def _default_keyboard(self) -> dict:
        """Backward compatibility: return default keyboard markup"""
        from backend.api.telegram.config import APPROVAL_YES
        return {
            "keyboard": [[
                {"text": "📊 Check Status"},
                {"text": "📸 Get Screenshot"},
            ], [
                {"text": "❓ Help & Guide"},
                {"text": "🟢 WhatsApp Link"},
            ]],
            "resize_keyboard": True,
        }

    async def _wa_cb_allow(self, chat_id: str, pending_id: str) -> None:
        """Backward compatibility: delegate to whatsapp module"""
        await self.whatsapp.allow_sender(chat_id, pending_id)

    async def _wa_cb_block(self, chat_id: str, pending_id: str) -> None:
        """Backward compatibility: delegate to whatsapp module"""
        await self.whatsapp.block_sender(chat_id, pending_id)

    async def _send_message(self, chat_id: str, text: str, **kwargs) -> None:
        """Backward compatibility: delegate to message_sender"""
        await self.message_sender.send_message(chat_id, text, **kwargs)

    async def _send_screenshot(self, chat_id: str, caption: str) -> None:
        """Backward compatibility: delegate to typing_indicator"""
        await self.typing_indicator.send_screenshot(chat_id, caption)

    async def _cb_confirm_shutdown(self, chat_id: str) -> None:
        """Backward compatibility: delegate to callback_handler"""
        await self.callback_handler.confirm_dangerous_command(chat_id)

    async def _handle_pairing(self, chat_id: str, text: str) -> None:
        """Handle pairing request from unpaired user"""
        # Extract code from message
        parts = text.strip().split()
        if len(parts) < 2:
            await self._send_message(chat_id, "Usage: /pair YOUR_CODE")
            return
        
        code = parts[1].strip()
        if code == self.pairing_code:
            self.chat_id = chat_id
            # Save to database
            try:
                from backend.database.connection import SessionLocal
                from backend.database.models import UserPreferences
                from backend.database.crypto import crypto_manager
                
                with SessionLocal() as db:
                    pref = db.query(UserPreferences).first()
                    if pref:
                        pref.telegram_chat_id = crypto_manager.encrypt(chat_id)
                        db.commit()
            except Exception as e:
                logger.error(f"Failed to save pairing: {e}")
            
            copy = self._wa_ui_copy(get_latest_conversation_style())
            await self._send_message(chat_id, copy["pairing_success"], reply_markup=self._default_keyboard())
        else:
            await self._send_message(chat_id, "❌ Invalid pairing code.")

    async def _complete_manual_wa_reply(self, chat_id: str, pending_id: str, text: str) -> None:
        """Complete manual WhatsApp reply workflow"""
        self._wa_manual_awaiting.pop(chat_id, None)
        timer = self._wa_manual_timers.pop(pending_id, None)
        if timer:
            timer.cancel()
        
        pending = self._pending_wa.pop(pending_id, None)
        if not pending:
            return
        
        # Send reply via WhatsApp
        try:
            from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
            if whatsapp_manager:
                whatsapp_manager.reply_to_chat(pending.chat_id_wa, text)
                copy = self._wa_ui_copy(self._chat_language_style(chat_id))
                await self._send_message(chat_id, copy["reply_sent"], reply_markup=self._default_keyboard())
        except Exception as e:
            logger.error(f"Failed to send WA reply: {e}")
            copy = self._wa_ui_copy(self._chat_language_style(chat_id))
            await self._send_message(chat_id, copy["reply_failed"], reply_markup=self._default_keyboard())

    async def _send_task_status(self, chat_id: str) -> None:
        """Send current task status to user"""
        state = self._task_states.get(chat_id)
        if not state:
            await self._send_message(chat_id, "No active task found.")
            return
        
        elapsed = time.monotonic() - state.started_at
        elapsed_str = f"{int(elapsed)}s"
        
        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        
        if state.state == "completed":
            msg = copy["task_completed_status"].format(elapsed=elapsed_str)
        elif state.state == "timed_out":
            msg = copy["task_timed_out_status"].format(elapsed=elapsed_str)
        elif state.state == "failed":
            msg = copy["task_failed_status"].format(detail=state.error or "Unknown error")
        elif state.state == "cancelled":
            msg = copy["task_cancelled_status"]
        else:
            location = "background " if state.backgrounded else ""
            msg = copy["task_running"].format(
                location=location,
                elapsed=elapsed_str,
                stage=state.status or "Working..."
            )
        
        await self._send_message(chat_id, msg)

    async def _handle_wa_pair(self, chat_id: str, text: str) -> None:
        """Handle WhatsApp pairing request"""
        parts = text.strip().split()
        if len(parts) < 2:
            copy = self._wa_ui_copy(self._chat_language_style(chat_id))
            await self._send_message(chat_id, copy["valid_phone_required"])
            return
        
        phone = parts[1].strip()
        # Remove leading + if present
        if phone.startswith("+"):
            phone = phone[1:]
        
        # Add country code if missing (assume India 91)
        if len(phone) == 10:
            phone = "91" + phone
        
        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        await self._send_message(chat_id, copy["wa_code_requesting"].format(phone=phone))
        
        try:
            from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
            if whatsapp_manager:
                code = whatsapp_manager.request_pairing_code(phone)
                if code:
                    await self._send_message(
                        chat_id,
                        copy["wa_code_instructions"].format(code=code)
                    )
                else:
                    await self._send_message(chat_id, copy["wa_code_not_found"])
            else:
                await self._send_message(chat_id, copy["wa_code_not_found"])
        except Exception as e:
            logger.error(f"WA pairing failed: {e}")
            await self._send_message(chat_id, copy["wa_code_not_found"])

    async def _send_help(self, chat_id: str) -> None:
        """Send help message (delegates to CommandHandler)."""
        await self.command_handler.send_help(chat_id)

    async def _unpair(self, chat_id: str) -> None:
        """Unpair Telegram bot (delegates to CommandHandler)."""
        await self.command_handler.unpair(chat_id)

    async def _send_status(self, chat_id: str) -> None:
        """Send system status (delegates to CommandHandler)."""
        await self.command_handler.send_status(chat_id)

    async def _lock_microphone(self, chat_id: str) -> None:
        """Lock microphone (delegates to CommandHandler)."""
        await self.command_handler.lock_microphone(chat_id)

    async def _unlock_microphone(self, chat_id: str) -> None:
        """Unlock microphone (delegates to CommandHandler)."""
        await self.command_handler.unlock_microphone(chat_id)

    async def _emergency_stop(self, chat_id: str) -> None:
        """Trigger emergency stop (delegates to CommandHandler)."""
        await self.command_handler.emergency_stop(chat_id)

    async def _send_wa_link_guide(self, chat_id: str) -> None:
        """Send WhatsApp linking guide (delegates to CommandHandler)."""
        await self.command_handler.send_wa_link_guide(chat_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Task processing (delegate to TaskHandler)
    # ──────────────────────────────────────────────────────────────────────────

    async def _process_and_reply(
        self,
        chat_id: str,
        text: str,
        session_id: str,
        sent_msg_id: int | None = None,
    ) -> None:
        """
        Process user message and generate reply (delegated to TaskHandler).
        
        This method orchestrates the complete task lifecycle:
        - Isolate voice channel to prevent interference
        - Route through gateway with streaming callbacks
        - Handle tool approval requests
        - Display progress updates
        - Handle timeout transitions (foreground -> background -> hard timeout)
        - Process special signals (system_state, mode_change)
        - Send final response
        - Auto-screenshot for visual commands
        - Restore voice channel on completion
        
        Args:
            chat_id: Telegram chat ID
            text: User message text
            session_id: Session identifier
            sent_msg_id: Optional existing message ID for editing
        """
        await self.task_handler.process_and_reply(
            chat_id, text, session_id, sent_msg_id
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Core loops (delegate to polling/WhatsApp managers)
    # ──────────────────────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Main long-polling loop (delegated to PollingManager)."""
        await self.polling.poll_loop()

    async def _wa_listener_loop(self) -> None:
        """
        WhatsApp message listener loop.
        
        Starts the WhatsApp incoming message listener and registers our handler.
        Automatically restarts on clean exits with exponential backoff on errors.
        """
        retry_delay = 5.0
        max_delay = 300.0  # 5 minutes

        while self.running:
            try:
                from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager

                wa_status = whatsapp_manager.get_status()
                # Start the listener for ANY state where the service is up.
                # The bridge can legitimately report 'connected', 'authenticated',
                # 'running', or other valid states — do NOT hard-code specific
                # strings here or incoming messages will be silently dropped.
                service_up = (
                    self.chat_id
                    and whatsapp_manager
                    and wa_status.get("available", False)
                    and wa_status.get("status") not in (
                        "unavailable", "consent_required", "qr", "error", None
                    )
                )
                if service_up:
                    logger.info(
                        "[TelegramBot] Starting WhatsApp listener (bridge status=%s).",
                        wa_status.get("status")
                    )
                    await whatsapp_manager.start_incoming_listener(
                        self.whatsapp.handle_whatsapp_incoming
                    )
                    retry_delay = 5.0  # reset on clean exit
                else:
                    logger.debug(
                        "[TelegramBot] WhatsApp not ready (status=%s). Retrying in 10s.",
                        wa_status.get("status")
                    )
                    await asyncio.sleep(10.0)

            except asyncio.CancelledError:
                logger.info("[TelegramBot] WhatsApp listener cancelled.")
                break
            except Exception as exc:
                logger.error(
                    "[TelegramBot] WhatsApp listener crashed: %s — "
                    "restarting in %.1fs",
                    exc, retry_delay, exc_info=True
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, max_delay)

    async def _wa_cleanup_loop(self) -> None:
        """
        Periodic cleanup of stale pending WhatsApp messages.
        
        Removes WhatsApp messages that have been pending for too long
        (default: 30 minutes) to prevent memory leaks.
        """
        from backend.api.telegram.whatsapp.notification import MANUAL_TIMEOUT
        WA_EXPIRE_SECS = 1800  # 30 minutes
        WA_CLEANUP_INT = 300   # check every 5 minutes

        while self.running:
            try:
                await asyncio.sleep(WA_CLEANUP_INT)
                if not self.running:
                    break
                    
                now = time.time()
                expired = [
                    pid for pid, p in self._pending_wa.items()
                    if (now - p.created_at) > WA_EXPIRE_SECS
                ]
                
                for pid in expired:
                    self._pending_wa.pop(pid, None)
                    self._wa_manual_timers.pop(pid, None)
                    logger.info(
                        "[TelegramBot] Removed expired WhatsApp pending_id=%s", pid
                    )
                    
            except asyncio.CancelledError:
                logger.info("[TelegramBot] WhatsApp cleanup loop cancelled.")
                break
            except Exception as exc:
                logger.error(
                    "[TelegramBot] WhatsApp cleanup error: %s", exc, exc_info=True
                )
                await asyncio.sleep(60.0)

    # ──────────────────────────────────────────────────────────────────────────
    # Message and callback routing (delegate to handlers)
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_message(self, message: dict) -> None:
        """Route incoming message to MessageHandler."""
        await self.message_handler.handle_message(message)

    async def _handle_callback_query(self, cq: dict) -> None:
        """Route callback query to CallbackHandler."""
        await self.callback_handler.handle_callback_query(cq)

    # ──────────────────────────────────────────────────────────────────────────
    # Backward compatibility wrappers
    # ──────────────────────────────────────────────────────────────────────────

    async def _send_message(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: Optional[dict] = None,
        parse_mode: str = "Markdown",
    ) -> None:
        """Send a message (delegates to MessageSender)."""
        await self.messaging.send_message(
            chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode
        )

    async def _send_message_get_id(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: Optional[str] = "Markdown",
    ) -> Optional[str]:
        """Send a message and return message_id (delegates to MessageSender)."""
        return await self.messaging.send_message_get_id(
            chat_id, text, parse_mode=parse_mode
        )

    async def _edit_message(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        *,
        reply_markup: Optional[dict] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> None:
        """Edit an existing message (delegates to MessageEditor)."""
        await self.editor.edit_message(
            chat_id, message_id, text,
            reply_markup=reply_markup, parse_mode=parse_mode
        )

    async def _send_typing(self, chat_id: str) -> None:
        """Send typing indicator (delegates to TypingIndicator)."""
        await self.typing_indicator.send_typing(chat_id)

    async def _answer_callback(self, callback_query_id: Optional[str]) -> None:
        """Answer a callback query (delegates to TypingIndicator)."""
        await self.typing_indicator.answer_callback(callback_query_id)

    async def _send_screenshot(self, chat_id: str, caption: str) -> None:
        """Send a screenshot (delegates to CommandHandler)."""
        await self.command_handler.send_screenshot(chat_id, caption)

    async def _send_help(self, chat_id: str) -> None:
        """Send help message (delegates to CommandHandler)."""
        await self.command_handler.send_help(chat_id)

    async def _send_status(self, chat_id: str) -> None:
        """Send system status (delegates to CommandHandler)."""
        await self.command_handler.send_status(chat_id)

    async def _send_wa_link_guide(self, chat_id: str) -> None:
        """Send WhatsApp link guide (delegates to CommandHandler)."""
        await self.command_handler.send_wa_link_guide(chat_id)

    async def _lock_microphone(self, chat_id: str) -> None:
        """Lock microphone (delegates to CommandHandler)."""
        await self.command_handler.lock_microphone(chat_id)

    async def _unlock_microphone(self, chat_id: str) -> None:
        """Unlock microphone (delegates to CommandHandler)."""
        await self.command_handler.unlock_microphone(chat_id)

    async def _emergency_stop(self, chat_id: str) -> None:
        """Trigger emergency stop (delegates to CommandHandler)."""
        await self.command_handler.emergency_stop(chat_id)

    async def _unpair(self, chat_id: str) -> None:
        """Unpair bot (delegates to CommandHandler)."""
        await self.command_handler.unpair(chat_id)

    # ──────────────────────────────────────────────────────────────────────────
    # WhatsApp delegation wrappers
    # ──────────────────────────────────────────────────────────────────────────

    async def _wa_cb_gemini(self, chat_id: str, pending_id: str) -> None:
        """Handle Gemini draft callback (delegates to WhatsAppNotification)."""
        await self.whatsapp.generate_gemini_draft(chat_id, pending_id)

    async def _wa_cb_send_draft(self, chat_id: str, pending_id: str) -> None:
        """Handle send draft callback (delegates to WhatsAppNotification)."""
        await self.whatsapp.send_draft(chat_id, pending_id)

    async def _wa_cb_manual(self, chat_id: str, pending_id: str) -> None:
        """Handle manual reply callback (delegates to WhatsAppNotification)."""
        await self.whatsapp.start_manual_reply(chat_id, pending_id)

    async def _wa_cb_ignore(self, chat_id: str, pending_id: str) -> None:
        """Handle ignore callback (delegates to WhatsAppNotification)."""
        await self.whatsapp.ignore_message(chat_id, pending_id)

    async def _wa_cb_allow(self, chat_id: str, pending_id: str) -> None:
        """Handle allow sender callback (delegates to WhatsAppNotification)."""
        await self.whatsapp.allow_sender(chat_id, pending_id)

    async def _wa_cb_block(self, chat_id: str, pending_id: str) -> None:
        """Handle block sender callback (delegates to WhatsAppNotification)."""
        await self.whatsapp.block_sender(chat_id, pending_id)

    async def _complete_manual_wa_reply(
        self, chat_id: str, pending_id: str, text: str
    ) -> None:
        """Complete manual WhatsApp reply (delegates to WhatsAppNotification)."""
        await self.whatsapp.complete_manual_reply(chat_id, pending_id, text)

    # ──────────────────────────────────────────────────────────────────────────
    # Utilities (may need to be extracted to utils module later)
    # ──────────────────────────────────────────────────────────────────────────

    def _default_keyboard(self) -> dict:
        """
        Get the default reply keyboard markup.
        
        Returns:
            Telegram keyboard markup dict with common action buttons
        """
        return {
            "keyboard": [
                ["❓ Help & Guide", "📊 Check Status"],
                ["📸 Get Screenshot", "🔑 WhatsApp Link"],
            ],
            "resize_keyboard": True,
        }

    @staticmethod
    def _wa_ui_copy(style: str) -> dict[str, str]:
        """
        Get localized UI copy for WhatsApp notifications.
        
        Args:
            style: Language style (BANGLISH, HINDILISH, or ENGLISH)
            
        Returns:
            Dictionary of localized UI strings
        """
        # Delegate to WhatsAppNotification's static method
        return WhatsAppNotification._wa_ui_copy(style)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton instance (for backward compatibility)
# ──────────────────────────────────────────────────────────────────────────────

telegram_bot_manager = TelegramBotManager()


