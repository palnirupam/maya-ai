"""
message_handler.py
==================
Telegram message routing and handling logic extracted from TelegramBotManager.

This module handles all incoming text messages from Telegram:
- Manual WhatsApp reply interception
- Pairing handshake for new users
- Authorization checks
- Language style detection and memory
- Approval/rejection for pending tool executions
- Task status requests
- WhatsApp pairing commands
- Static commands (/help, /status, /screenshot, etc.)
- Microphone lock/unlock (sleep mode)
- Emergency stop
- Routing to orchestrator for agent processing
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.api.telegram_bot import TelegramBotManager

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants (mirrored from telegram_bot.py)
# ──────────────────────────────────────────────────────────────────────────────

STOP_KEYWORDS = frozenset([
    "stop", "halt", "panic", "🛑 emergency stop",
    "thamo", "থামো", "থাম",
])
APPROVAL_YES = frozenset({"yes", "y", "yeah", "yep", "হ্যাঁ", "হ্যা", "হা", "জি", "করো", "execute"})
APPROVAL_NO = frozenset({"no", "n", "nope", "না", "cancel", "বাতিল", "করো না"})
TASK_STATUS_TTL = 900.0  # keep a backgrounded task's final status for 15 min


class MessageHandler:
    """
    Handles all incoming Telegram messages and routes them appropriately.
    
    This class encapsulates the entire message handling logic that was previously
    part of TelegramBotManager._handle_message. It maintains no state of its own;
    all state access is delegated to the manager instance.
    """

    def __init__(self, manager: TelegramBotManager):
        """
        Initialize the message handler with a reference to the bot manager.
        
        Args:
            manager: The TelegramBotManager instance that owns this handler
        """
        self.manager = manager

    async def handle_message(self, message: dict) -> None:
        """
        Main entry point for handling incoming Telegram messages.
        
        This method implements the complete message routing logic:
        1. Extract chat_id and text
        2. Check for manual WhatsApp reply intercept
        3. Handle pairing handshake for unpaired bots
        4. Reject unauthorized senders
        5. Remember user's language style
        6. Handle pending tool execution approval/rejection
        7. Handle task status requests
        8. Handle WhatsApp pairing commands
        9. Handle static commands (/help, /status, /screenshot, etc.)
        10. Handle microphone lock/unlock
        11. Handle emergency stop
        12. Route to orchestrator for agent processing
        
        Args:
            message: Raw Telegram message dict from the API
        """
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()
        if not text:
            return

        # ── Intercept manual WA reply ──────────────────────────────────────
        if pending_id := self.manager._wa_manual_awaiting.get(chat_id):
            if self.manager.chat_id and chat_id == self.manager.chat_id:
                await self.manager._complete_manual_wa_reply(chat_id, pending_id, text)
                return

        # ── Pairing handshake ──────────────────────────────────────────────
        if not self.manager.chat_id:
            await self.manager._handle_pairing(chat_id, text)
            return

        # ── Reject unauthorized senders ────────────────────────────────────
        if chat_id != self.manager.chat_id:
            await self.manager._send_message(
                chat_id,
                "❌ *Unauthorized.* This Maya AI instance is paired with another account.",
            )
            return

        self.manager._remember_chat_language_style(chat_id, text)
        text_lower = text.lower()

        # ── Approval/rejection for pending tool execution ──────────────────
        pending_req_id = self.manager._pending_exec_approval.get(chat_id)
        if pending_req_id and text_lower in APPROVAL_YES:
            self.manager._pending_exec_approval.pop(chat_id, None)
            from backend.brain.reasoning.tool_planner import tool_planner
            tool_planner.resolve_tool(
                pending_req_id,
                approved=True,
                user_id=f"telegram:{chat_id}",
            )
            copy = self.manager._wa_ui_copy(self.manager._chat_language_style(chat_id))
            await self.manager._send_message(chat_id, copy["approval_received"])
            return
        if pending_req_id and text_lower in APPROVAL_NO:
            self.manager._pending_exec_approval.pop(chat_id, None)
            from backend.brain.reasoning.tool_planner import tool_planner
            tool_planner.resolve_tool(
                pending_req_id,
                approved=False,
                user_id=f"telegram:{chat_id}",
            )
            copy = self.manager._wa_ui_copy(self.manager._chat_language_style(chat_id))
            await self.manager._send_message(
                chat_id,
                copy["command_cancelled"],
                reply_markup=self.manager._default_keyboard(),
            )
            return

        # ── Task status request ────────────────────────────────────────────
        # A short progress question belongs to the current/backgrounded task;
        # it must not cancel that task or enter the normal agent router.
        from backend.api.telegram.config import is_task_status_request
        if is_task_status_request(text):
            active = self.manager._active_tasks.get(chat_id)
            state = self.manager._task_states.get(chat_id)
            state_is_recent_background = bool(
                state
                and state.backgrounded
                and (time.monotonic() - state.updated_at) <= TASK_STATUS_TTL
            )
            if (active and not active.done()) or state_is_recent_background:
                await self.manager._send_task_status(chat_id)
                return

        # ── WhatsApp pairing command ───────────────────────────────────────
        # Check if message is /whatsapp_pair command
        if text_lower.startswith("/whatsapp_pair") or text_lower.startswith("whatsapp_pair"):
            await self.manager._handle_wa_pair(chat_id, text)
            return

        # ── Static commands / button taps ──────────────────────────────────
        if text_lower in {"/start", "/help", "❓ help & guide"}:
            await self.manager._send_help(chat_id)
            return
        if text_lower in {"/reset", "👤 unpair bot"}:
            await self.manager._unpair(chat_id)
            return
        if text_lower in {"/status", "📊 check status"}:
            await self.manager._send_status(chat_id)
            return
        if text_lower in {"/screenshot", "📸 get screenshot"}:
            await self.manager._send_screenshot(chat_id, "Here is your current desktop screen:")
            return
        if text_lower in {"/whatsapp_qr", "🟢 whatsapp qr", "🔑 whatsapp link"}:
            await self.manager._send_wa_link_guide(chat_id)
            return

        # ── Microphone Lock / Sleep Mode ───────────────────────────────────
        if text_lower in {"/lock", "🔒 mic lock", "lock mic", "sleep mode on",
                          "mic lock koro", "lock koro", "ঘুমাও", "lock"}:
            await self.manager._lock_microphone(chat_id)
            return
        if text_lower in {"/unlock", "🔓 mic unlock", "unlock mic", "sleep mode off",
                          "mic unlock koro", "unlock koro", "জাগো", "unlock"}:
            await self.manager._unlock_microphone(chat_id)
            return

        # ── Emergency stop ─────────────────────────────────────────────────
        if text_lower in STOP_KEYWORDS:
            await self.manager._emergency_stop(chat_id)
            return

        # ── Route to orchestrator ──────────────────────────────────────────
        session_id = f"telegram_{chat_id}"
        if (existing := self.manager._active_tasks.get(chat_id)) and not existing.done():
            existing.cancel()
            
        # Trigger on_session_start hook in the background
        from backend.system.hooks import trigger_hook
        asyncio.create_task(trigger_hook("on_session_start", {
            "chat_id": chat_id,
            "text": text,
            "session_id": session_id
        }))

        from backend.api.telegram_bot import TelegramTaskState
        self.manager._task_states[chat_id] = TelegramTaskState(
            original_text=text,
            session_id=session_id,
        )
        task = asyncio.create_task(
            self.manager._process_and_reply(chat_id, text, session_id),
            name=f"tg-reply-{chat_id}",
        )
        self.manager._active_tasks[chat_id] = task
