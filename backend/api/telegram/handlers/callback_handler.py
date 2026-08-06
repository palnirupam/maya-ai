"""
callback_handler.py
===================
Production-ready callback query handler for Maya AI Telegram bot.

Extracted from telegram_bot.py to improve modularity and separation of concerns.
Handles all inline button callbacks including WhatsApp actions, tool approval,
and system commands like shutdown confirmation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.api.telegram_bot import TelegramBotManager

logger = logging.getLogger(__name__)


class CallbackHandler:
    """
    Handles all Telegram callback queries (inline button presses).
    
    Responsibilities:
    - Route callbacks based on data prefix
    - Handle WhatsApp-related callbacks (gemini, send_draft, manual, ignore, allow, block)
    - Handle tool approval/denial callbacks (exec_approve_, exec_deny_)
    - Handle shutdown confirmation callbacks (confirm_shutdown, cancel_shutdown)
    - Enforce authorization (private chat vs group chat)
    - Trigger hooks for audit/logging purposes
    """

    def __init__(self, manager: TelegramBotManager):
        """
        Initialize the callback handler.
        
        Args:
            manager: Reference to the TelegramBotManager instance for accessing
                    bot methods and state.
        """
        self.manager = manager

    async def handle_callback_query(self, cq: dict) -> None:
        """
        Main entry point for handling Telegram callback queries.
        
        Processes inline button presses and routes them to appropriate handlers
        based on the callback data prefix.
        
        Args:
            cq: Callback query dictionary from Telegram API containing:
                - id: Callback query ID (for answering)
                - data: Callback data string (identifies which button was pressed)
                - message: Message object containing chat info
                - from: User who pressed the button
        
        Flow:
            1. Extract callback metadata (cq_id, data, chat_id, user_id)
            2. Answer callback immediately (removes loading spinner)
            3. Perform authorization check
            4. Route to specific handler based on data prefix
        """
        # ── Extract callback metadata ──────────────────────────────────────
        cq_id = cq.get("id")
        data = cq.get("data", "")
        chat_id = str(cq["message"]["chat"]["id"])
        callback_user_id = str(cq.get("from", {}).get("id", ""))

        # ── Answer callback immediately ────────────────────────────────────
        # This removes the loading spinner on the button in Telegram
        await self.manager._answer_callback(cq_id)

        # ── Authorization check ────────────────────────────────────────────
        # For private chats (not starting with "-"), only the owner can press buttons
        # For group chats, any member can press buttons (chat_id starts with "-")
        unauthorized_private_actor = bool(
            self.manager.chat_id
            and not self.manager.chat_id.startswith("-")
            and callback_user_id != self.manager.chat_id
        )
        
        if (
            not self.manager.chat_id
            or chat_id != self.manager.chat_id
            or unauthorized_private_actor
        ):
            logger.warning(
                "[CallbackHandler] Ignoring callback from unauthorized chat. "
                "chat_id=%s, configured_chat=%s, callback_user=%s",
                chat_id, self.manager.chat_id, callback_user_id
            )
            return

        # ── Route based on callback data prefix ────────────────────────────
        
        # WhatsApp callbacks
        if data.startswith("wa_gemini_"):
            await self._handle_wa_gemini(chat_id, data[len("wa_gemini_"):])
        elif data.startswith("wa_send_draft_"):
            await self._handle_wa_send_draft(chat_id, data[len("wa_send_draft_"):])
        elif data.startswith("wa_manual_"):
            await self._handle_wa_manual(chat_id, data[len("wa_manual_"):])
        elif data.startswith("wa_ignore_"):
            await self._handle_wa_ignore(chat_id, data[len("wa_ignore_"):])
        elif data.startswith("wa_allow_"):
            await self._handle_wa_allow(chat_id, data[len("wa_allow_"):])
        elif data.startswith("wa_block_"):
            await self._handle_wa_block(chat_id, data[len("wa_block_"):])
        
        # Shutdown confirmation callbacks
        elif data == "confirm_shutdown":
            await self._handle_confirm_shutdown(chat_id)
        elif data == "cancel_shutdown":
            await self._handle_cancel_shutdown(chat_id)
        
        # Tool approval callbacks
        elif data.startswith("exec_approve_"):
            await self._handle_exec_approve(chat_id, cq, data)
        elif data.startswith("exec_deny_"):
            await self._handle_exec_deny(chat_id, cq, data)
        
        # Task cancellation callbacks (NEW)
        elif data.startswith("cancel_task_"):
            await self._handle_cancel_task(chat_id, cq, data)
        
        else:
            logger.warning(
                "[CallbackHandler] Unknown callback data: %s from chat_id=%s",
                data, chat_id
            )

    # ──────────────────────────────────────────────────────────────────────────
    # WhatsApp callback handlers
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_wa_gemini(self, chat_id: str, pending_id: str) -> None:
        """
        Handle 'Use Gemini Draft' button for WhatsApp replies.
        Delegates to the manager's WhatsApp callback handler.
        """
        await self.manager._wa_cb_gemini(chat_id, pending_id)

    async def _handle_wa_send_draft(self, chat_id: str, pending_id: str) -> None:
        """
        Handle 'Send Draft' button for WhatsApp replies.
        Delegates to the manager's WhatsApp callback handler.
        """
        await self.manager._wa_cb_send_draft(chat_id, pending_id)

    async def _handle_wa_manual(self, chat_id: str, pending_id: str) -> None:
        """
        Handle 'Manual Reply' button for WhatsApp replies.
        Delegates to the manager's WhatsApp callback handler.
        """
        await self.manager._wa_cb_manual(chat_id, pending_id)

    async def _handle_wa_ignore(self, chat_id: str, pending_id: str) -> None:
        """
        Handle 'Ignore' button for WhatsApp messages.
        Delegates to the manager's WhatsApp callback handler.
        """
        await self.manager._wa_cb_ignore(chat_id, pending_id)

    async def _handle_wa_allow(self, chat_id: str, pending_id: str) -> None:
        """
        Handle 'Allow' button for new WhatsApp contacts.
        Delegates to the manager's WhatsApp callback handler.
        """
        await self.manager._wa_cb_allow(chat_id, pending_id)

    async def _handle_wa_block(self, chat_id: str, pending_id: str) -> None:
        """
        Handle 'Block' button for WhatsApp contacts.
        Delegates to the manager's WhatsApp callback handler.
        """
        await self.manager._wa_cb_block(chat_id, pending_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Shutdown confirmation handlers
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_confirm_shutdown(self, chat_id: str) -> None:
        """
        Handle 'Confirm Shutdown' button.
        Delegates to the manager's shutdown confirmation handler.
        """
        await self.manager._cb_confirm_shutdown(chat_id)

    async def _handle_cancel_shutdown(self, chat_id: str) -> None:
        """
        Handle 'Cancel Shutdown' button.
        Delegates to the manager's shutdown cancellation handler.
        """
        await self.manager._cb_cancel_shutdown(chat_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Tool approval handlers
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_exec_approve(
        self, chat_id: str, cq: dict, data: str
    ) -> None:
        """
        Handle tool execution approval.
        
        When user clicks 'Approve' button on a tool execution request:
        1. Extract request ID from callback data
        2. Remove from pending approval queue
        3. Resolve the tool approval in tool_planner
        4. Trigger on_command_approval_decision hook
        5. Edit the approval message to show approval status
        
        Args:
            chat_id: Telegram chat ID
            cq: Full callback query dict (for extracting user info)
            data: Callback data string (format: "exec_approve_<req_id>")
        """
        req_id = data[len("exec_approve_"):]
        
        # Remove from pending approval tracking
        if self.manager._pending_exec_approval.get(chat_id) == req_id:
            self.manager._pending_exec_approval.pop(chat_id, None)
        
        # Extract user identifier (prefer username, fallback to user_id)
        user_id = str(
            cq["from"].get("username", cq["from"].get("id", "telegram_user"))
        )
        
        # Resolve the tool approval in tool_planner
        from backend.brain.reasoning.tool_planner import tool_planner
        tool_planner.resolve_tool(req_id, approved=True, user_id=user_id)
        
        # Trigger hook for audit/logging purposes
        from backend.system.hooks import trigger_hook
        asyncio.create_task(
            trigger_hook(
                "on_command_approval_decision",
                {
                    "request_id": req_id,
                    "approved": True,
                    "user_id": user_id,
                    "chat_id": chat_id,
                },
            )
        )
        
        # Update the approval message to show approval status
        await self.manager._edit_message(
            chat_id,
            str(cq["message"]["message_id"]),
            "✅ *Command Approved.* Executing...",
            parse_mode="Markdown",
        )
        
        logger.info(
            "[CallbackHandler] Tool approved: req_id=%s, user_id=%s, chat_id=%s",
            req_id, user_id, chat_id
        )

    async def _handle_exec_deny(
        self, chat_id: str, cq: dict, data: str
    ) -> None:
        """
        Handle tool execution denial.
        
        When user clicks 'Deny' button on a tool execution request:
        1. Extract request ID from callback data
        2. Remove from pending approval queue
        3. Resolve the tool denial in tool_planner
        4. Trigger on_command_approval_decision hook
        5. Edit the approval message to show denial status
        
        Args:
            chat_id: Telegram chat ID
            cq: Full callback query dict (for extracting user info)
            data: Callback data string (format: "exec_deny_<req_id>")
        """
        req_id = data[len("exec_deny_"):]
        
        # Remove from pending approval tracking
        if self.manager._pending_exec_approval.get(chat_id) == req_id:
            self.manager._pending_exec_approval.pop(chat_id, None)
        
        # Extract user identifier (prefer username, fallback to user_id)
        user_id = str(
            cq["from"].get("username", cq["from"].get("id", "telegram_user"))
        )
        
        # Resolve the tool denial in tool_planner
        from backend.brain.reasoning.tool_planner import tool_planner
        tool_planner.resolve_tool(req_id, approved=False, user_id=user_id)
        
        # Trigger hook for audit/logging purposes
        from backend.system.hooks import trigger_hook
        asyncio.create_task(
            trigger_hook(
                "on_command_approval_decision",
                {
                    "request_id": req_id,
                    "approved": False,
                    "user_id": user_id,
                    "chat_id": chat_id,
                },
            )
        )
        
        # Update the approval message to show denial status
        await self.manager._edit_message(
            chat_id,
            str(cq["message"]["message_id"]),
            "❌ *Command Denied.* Execution aborted.",
            parse_mode="Markdown",
        )
        
        logger.info(
            "[CallbackHandler] Tool denied: req_id=%s, user_id=%s, chat_id=%s",
            req_id, user_id, chat_id
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Task Cancellation Handler (NEW)
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_cancel_task(
        self, chat_id: str, cq: dict, data: str
    ) -> None:
        """
        Handle task cancellation request.
        
        When user clicks 'Cancel Task' button on a progress message:
        1. Parse callback data to extract chat_id and session_id
        2. Cancel the active task for this chat
        3. Update task state to cancelled
        4. Edit the progress message to show cancellation status
        5. Log the cancellation action
        
        Args:
            chat_id: Telegram chat ID
            cq: Full callback query dict (for extracting user info)
            data: Callback data string (format: "cancel_task_<chat_id>_<session_id>")
        """
        try:
            # Parse callback data: "cancel_task_<chat_id>_<session_id>"
            parts = data.split("_", 2)
            if len(parts) < 3:
                logger.warning(f"Invalid cancel_task callback data: {data}")
                return
            
            target_chat_id = parts[2]
            # session_id = parts[3] if len(parts) > 3 else None  # Optional for future use
            
            # Verify the user is cancelling their own task
            if target_chat_id != chat_id:
                logger.warning(
                    f"User {chat_id} tried to cancel task for {target_chat_id}"
                )
                return
            
            # Extract user identifier for logging
            user_id = str(
                cq["from"].get("username", cq["from"].get("id", "telegram_user"))
            )
            
            # Cancel the active task
            active_task = self.manager._active_tasks.get(chat_id)
            if active_task and not active_task.done():
                active_task.cancel()
                logger.info(
                    f"[CallbackHandler] Task cancelled by user: chat_id={chat_id}, user_id={user_id}"
                )
            
            # Update task state
            task_state = self.manager._task_states.get(chat_id)
            if task_state:
                task_state.state = "cancelled"
                task_state.status = "Cancelled by user"
                task_state.updated_at = time.monotonic()
            
            # Update the progress message to show cancellation
            await self.manager.message_editor.edit_message(
                chat_id,
                str(cq["message"]["message_id"]),
                "🛑 **Task Cancelled**\n\nThe task has been stopped at your request.",
                parse_mode="Markdown",
            )
            
            # Send confirmation message
            copy = self.manager._wa_ui_copy(
                self.manager._chat_language_style(chat_id)
            )
            await self.manager.message_sender.send_message(
                chat_id,
                copy.get("command_cancelled", "❌ Task has been cancelled."),
                reply_markup=self.manager._default_keyboard(),
            )
            
            logger.info(
                "[CallbackHandler] Task cancellation completed: chat_id=%s, user_id=%s",
                chat_id, user_id
            )
            
        except Exception as e:
            logger.error(f"Error handling task cancellation: {e}", exc_info=True)
            # Send error message to user
            await self.manager.message_sender.send_message(
                chat_id,
                "❌ Error cancelling task. Please try again or use `/stop`.",
            )
