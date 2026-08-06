"""
notification.py
===============
WhatsApp notification handling for Telegram bot integration.

Extracted from telegram_bot.py to provide clean separation of WhatsApp
integration functionality.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

from backend.brain.language_style import (
    BANGLISH,
    ENGLISH,
    HINDILISH,
    detect_language_style,
    get_latest_conversation_style,
    response_style_directive,
)
from backend.api.telegram.core.state_models import PendingWAReply

if TYPE_CHECKING:
    from backend.api.telegram.manager import TelegramBotManager

logger = logging.getLogger(__name__)

# Constants
MANUAL_TIMEOUT = 300.0  # 5 minutes - auto-cancel WA manual reply


class WhatsAppNotification:
    """
    Handles incoming WhatsApp message notifications and forwarding them
    to Telegram for user interaction.
    
    This class manages:
    - Building notification messages with proper formatting
    - Creating interactive buttons for reply options
    - Handling Gemini draft generation
    - Managing manual reply workflows
    - Sender authorization (allow/block)
    """

    def __init__(self, manager: "TelegramBotManager"):
        """
        Initialize the WhatsApp notification handler.

        Args:
            manager: Reference to the parent TelegramBotManager instance
        """
        self.manager = manager

    async def handle_whatsapp_incoming(self, msg_data: dict) -> None:
        """
        Called by the WA listener; sends a Telegram notification.
        
        Creates a PendingWAReply object from the incoming message data
        and sends a formatted notification to Telegram with action buttons.

        Args:
            msg_data: Dictionary containing WhatsApp message data:
                - id: Unique message identifier
                - chatId: WhatsApp chat identifier
                - fromNumber: Sender's phone number
                - fromName: Sender's display name
                - isGroup: Whether the message is from a group
                - groupName: Name of the group (if applicable)
                - triggerMsg: The actual message content
                - contextMessages: List of previous messages for context
                - isKnown: Whether the sender is in the known contacts list
        """
        if not self.manager.chat_id:
            return

        pending = PendingWAReply(
            id              = msg_data.get("id", str(time.time())),
            chat_id_wa      = msg_data.get("chatId", ""),
            from_number     = msg_data.get("fromNumber", "unknown"),
            from_name       = msg_data.get("fromName", msg_data.get("fromNumber", "?")),
            is_group        = msg_data.get("isGroup", False),
            group_name      = msg_data.get("groupName", "Unknown Group"),
            trigger_msg     = msg_data.get("triggerMsg", ""),
            context_messages= msg_data.get("contextMessages", []),
            is_known        = msg_data.get("isKnown", False),
        )
        self.manager._pending_wa[pending.id] = pending

        style = get_latest_conversation_style()
        text, markup = self.build_wa_notification(pending, style)
        await self.manager.message_sender.send_message(self.manager.chat_id, text, reply_markup=markup)

    @staticmethod
    def _wa_ui_copy(style: str) -> dict[str, str]:
        """
        Get localized UI text for WhatsApp notifications based on conversation style.

        Args:
            style: Language style (BANGLISH, HINDILISH, or ENGLISH)

        Returns:
            Dictionary of localized UI strings
        """
        if style == BANGLISH:
            return {
                "unknown_title": "Unknown number theke WhatsApp message!",
                "unknown_tag": "ochena",
                "allow": "Allow koro",
                "manual": "Nije likhi",
                "group_title": "Group-e mention!",
                "context_none": "[Context: nei]",
                "group_warning": "GROUP MESSAGE - reply deyar age bhalo kore dekho!",
                "direct_title": "Notun WhatsApp message!",
                "authorization_required": "Age sender-ke allow koro; tar age WhatsApp reply create ba send kora jabe na.",
                "drafting": "Gemini draft create korchi...",
                "draft_empty": "Gemini empty reply diyeche.",
                "no_draft": "Kono draft paoa gelo na.",
                "send_draft": "Eta pathao",
                "edit": "Edit koro",
                "cancel": "Cancel",
                "manual_prompt": "*Reply type koro:*\n_(Pach minute time ache)_",
                "ignored": "*Ignored.* WhatsApp-e kono reply jabe na.",
                "allow_failed": "WhatsApp sender-ke allow kora gelo na. Service connection check koro.",
                "allow_success": "*+{number} allow kora hoyeche!* Future notification-e known sender hisebe dhora hobe.\n\nReply option choose koro:",
                "block_failed": "WhatsApp sender-ke block kora gelo na. Service connection check koro.",
                "block_success": "*+{number} block kora hoyeche!* Ei number theke ar notification asbe na.",
                "manual_timeout": "*Timeout* - manual reply cancel hoyeche.",
                "reply_sent": "*Reply sent!*",
                "reply_failed": "WhatsApp-e reply pathano gelo na. WhatsApp connected ache?",
            }
        if style == HINDILISH:
            return {
                "unknown_title": "Unknown number se WhatsApp message!",
                "unknown_tag": "anjaan",
                "allow": "Allow karo",
                "manual": "Khud likhu",
                "group_title": "Group me mention!",
                "context_none": "[Context: nahi]",
                "group_warning": "GROUP MESSAGE - reply karne se pehle dhyan se dekho!",
                "direct_title": "Naya WhatsApp message!",
                "authorization_required": "Pehle sender ko allow karo; usse pehle WhatsApp reply create ya send nahi hoga.",
                "drafting": "Gemini draft bana raha hoon...",
                "draft_empty": "Gemini ne empty reply diya.",
                "no_draft": "Koi draft nahi mila.",
                "send_draft": "Ye bhejo",
                "edit": "Edit karo",
                "cancel": "Cancel",
                "manual_prompt": "*Apna reply type karo:*\n_(Paanch minute ka time hai)_",
                "ignored": "*Ignored.* WhatsApp par koi reply nahi bheja jayega.",
                "allow_failed": "WhatsApp sender ko allow nahi kiya ja saka. Service connection check karo.",
                "allow_success": "*+{number} allow ho gaya!* Future notifications me ise known sender mana jayega.\n\nReply option choose karo:",
                "block_failed": "WhatsApp sender ko block nahi kiya ja saka. Service connection check karo.",
                "block_success": "*+{number} block ho gaya!* Is number se ab notification nahi aayega.",
                "manual_timeout": "*Timeout* - manual reply cancel ho gaya.",
                "reply_sent": "*Reply sent!*",
                "reply_failed": "WhatsApp par reply nahi bheja ja saka. WhatsApp connected hai?",
            }
        return {
            "unknown_title": "WhatsApp message from an unknown number!",
            "unknown_tag": "unknown",
            "allow": "Allow",
            "manual": "Write reply",
            "group_title": "Group mention!",
            "context_none": "[Context: none]",
            "group_warning": "GROUP MESSAGE - review it carefully before replying!",
            "direct_title": "New WhatsApp message!",
            "authorization_required": "Allow the sender first; no WhatsApp reply can be created or sent before that.",
            "drafting": "Creating a Gemini draft...",
            "draft_empty": "Gemini returned an empty reply.",
            "no_draft": "No draft was found.",
            "send_draft": "Send this",
            "edit": "Edit",
            "cancel": "Cancel",
            "manual_prompt": "*Type your reply:*\n_(You have five minutes)_",
            "ignored": "*Ignored.* No WhatsApp reply will be sent.",
            "allow_failed": "The WhatsApp sender could not be allowed. Check the service connection.",
            "allow_success": "*+{number} allowed!* Future notifications from this sender will be treated as known.\n\nChoose a reply option:",
            "block_failed": "The WhatsApp sender could not be blocked. Check the service connection.",
            "block_success": "*+{number} blocked!* No more notifications will be shown from this number.",
            "manual_timeout": "*Timeout* - manual reply cancelled.",
            "reply_sent": "*Reply sent!*",
            "reply_failed": "The WhatsApp reply could not be sent. Is WhatsApp connected?",
        }

    def build_wa_notification(
        self, p: PendingWAReply, style: str = ENGLISH
    ) -> tuple[str, dict]:
        """
        Build a formatted Telegram notification message for an incoming WhatsApp message.

        Creates appropriate message text and inline keyboard buttons based on:
        - Whether the sender is known or unknown
        - Whether it's a group message or direct message
        - Available context messages

        Args:
            p: PendingWAReply object containing message details
            style: Language style for UI text (BANGLISH, HINDILISH, or ENGLISH)

        Returns:
            Tuple of (message_text, reply_markup_dict)
        """
        copy = self._wa_ui_copy(style)

        reply_row = [
            {"text": "🤖 Gemini Draft", "callback_data": f"wa_gemini_{p.id}"},
            {"text": f"✏️ {copy['manual']}", "callback_data": f"wa_manual_{p.id}"},
            {"text": "❌ Ignore", "callback_data": f"wa_ignore_{p.id}"},
        ]

        if not p.is_known and not p.is_group:
            # Unknown sender - show allow/block options
            text = (
                f"📩 *{copy['unknown_title']}*\n\n"
                f"👤 {p.from_name} (+{p.from_number}) _({copy['unknown_tag']})_\n"
                f"─────────────────────────\n"
                f'"{p.trigger_msg}"\n'
                "─────────────────────────"
            )
            markup = {
                "inline_keyboard": [[
                    {"text": f"✅ {copy['allow']}", "callback_data": f"wa_allow_{p.id}"},
                    {"text": "🚫 Block", "callback_data": f"wa_block_{p.id}"},
                    {"text": "❌ Ignore", "callback_data": f"wa_ignore_{p.id}"},
                ]]
            }
        elif p.is_group:
            # Group message - show context and warning
            context_count = len(p.context_messages)
            if not context_count:
                ctx = copy["context_none"]
            elif style == BANGLISH:
                ctx = f"[Context: {context_count}-ta ager message]"
            elif style == HINDILISH:
                ctx = f"[Context: {context_count} pichhle message]"
            else:
                suffix = "" if context_count == 1 else "s"
                ctx = f"[Context: {context_count} previous message{suffix}]"
            
            text = (
                f"💬 *{copy['group_title']}*\n\n"
                f"👥 *Group:* {p.group_name}\n"
                f"👤 *Sender:* {p.from_name} (+{p.from_number})\n"
                f"─────────────────────────\n"
                f"{ctx}\n"
                f"─────────────────────────\n"
                f'"{p.trigger_msg}"\n'
                "─────────────────────────\n"
                f"⚠️ {copy['group_warning']}"
            )
            markup = {"inline_keyboard": [reply_row]}
        else:
            # Known sender - direct message
            text = (
                f"💬 *{copy['direct_title']}*\n\n"
                f"👤 *From:* {p.from_name} (+{p.from_number})\n"
                "📍 *Chat:* Personal (Direct)\n"
                f"─────────────────────────\n"
                f'"{p.trigger_msg}"\n'
                "─────────────────────────"
            )
            markup = {"inline_keyboard": [reply_row]}

        return text, markup

    async def require_wa_reply_authorization(
        self, chat_id: str, pending: PendingWAReply
    ) -> bool:
        """
        Check if reply authorization is required and notify user if needed.

        Unknown direct senders must be allowed before replying to prevent
        accidental replies to unknown/spam contacts.

        Args:
            chat_id: Telegram chat ID
            pending: PendingWAReply object

        Returns:
            True if authorized to reply, False if authorization required
        """
        if pending.is_group or pending.is_known:
            return True
        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        await self.manager.message_sender.send_message(
            chat_id,
            copy["authorization_required"],
            reply_markup=self.manager._default_keyboard(),
        )
        return False

    async def generate_gemini_draft(self, chat_id: str, pending_id: str) -> None:
        """
        Generate a draft reply using Gemini AI based on WhatsApp message context.

        Args:
            chat_id: Telegram chat ID to send the draft to
            pending_id: ID of the pending WhatsApp message
        """
        pending = self.manager._pending_wa.get(pending_id)
        if not pending:
            await self.manager.message_sender.send_message(
                chat_id, "⚠️ Pending message not found (expired?)."
            )
            return
        if not await self.require_wa_reply_authorization(chat_id, pending):
            return

        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        await self.manager.message_sender.send_message(chat_id, f"⏳ {copy['drafting']}")

        context_lines = "".join(
            f"[{m.get('name', m.get('from', '?'))}]: {m.get('body', '')}\n"
            for m in pending.context_messages
        )
        prompt = (
            "You are Maya, the user's personal AI assistant managing their WhatsApp.\n"
            "Respond naturally, casually, and friendly like a human assistant.\n"
            "CRITICAL: DO NOT sound like a robotic customer service bot. DO NOT say 'How can I help you?'.\n\n"
            "🌐 LANGUAGE RULE:\n"
            f"- {response_style_directive(detect_language_style(pending.trigger_msg))}\n"
            "- Maya supports Banglish, Hindilish, and English; all replies use Latin letters.\n\n"
            "Style: short, conversational, plain text only — like a real WhatsApp message. No markdown.\n\n"
            f"[Previous conversation — context only]\n"
            f"{context_lines or '(no prior context)'}\n"
            f"[Reply ONLY to this message]\n"
            f"{pending.trigger_msg}\n"
            f"[from: {pending.from_name} (+{pending.from_number})]\n\n"
            "Generate ONLY the reply text. No preamble."
        )

        draft = ""
        try:
            # Route through the shared channel gateway
            from backend.brain.gateway import run_turn
            result = await run_turn(f"wa_draft_{pending_id}", prompt)
            draft = result.final_text
        except Exception as exc:
            await self.manager.message_sender.send_message(
                chat_id, f"❌ Gemini error: {exc}",
                reply_markup=self.manager._default_keyboard(),
            )
            return

        if not draft:
            await self.manager.message_sender.send_message(
                chat_id, f"❌ {copy['draft_empty']}",
                reply_markup=self.manager._default_keyboard(),
            )
            return

        lang_hint = self._detect_language_hint(pending.trigger_msg)
        pending.gemini_draft = draft

        markup = {
            "inline_keyboard": [[
                {"text": f"✅ {copy['send_draft']}", "callback_data": f"wa_send_draft_{pending_id}"},
                {"text": f"✏️ {copy['edit']}", "callback_data": f"wa_manual_{pending_id}"},
                {"text": f"❌ {copy['cancel']}", "callback_data": f"wa_ignore_{pending_id}"},
            ]]
        }
        await self.manager.message_sender.send_message(
            chat_id,
            f"📝 *Gemini Draft Ready:*\n{lang_hint}\n\n`{draft}`",
            reply_markup=markup,
        )

    async def send_draft(self, chat_id: str, pending_id: str) -> None:
        """Send the Gemini-generated draft reply to WhatsApp."""
        pending = self.manager._pending_wa.get(pending_id)
        if not pending:
            await self.manager.message_sender.send_message(
                chat_id, "⚠️ Pending message not found (expired?)."
            )
            return
        if not await self.require_wa_reply_authorization(chat_id, pending):
            return
        if not pending.gemini_draft:
            copy = self._wa_ui_copy(self._chat_language_style(chat_id))
            await self.manager.message_sender.send_message(chat_id, f"❌ {copy['no_draft']}")
            return
        await self._send_wa_reply(chat_id, pending, pending.gemini_draft)

    async def start_manual_reply(self, chat_id: str, pending_id: str) -> None:
        """Initiate manual reply mode for a WhatsApp message."""
        pending = self.manager._pending_wa.get(pending_id)
        if not pending:
            await self.manager.message_sender.send_message(
                chat_id, "⚠️ Pending message not found (expired?)."
            )
            return
        if not await self.require_wa_reply_authorization(chat_id, pending):
            return
        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        self.manager._wa_manual_awaiting[chat_id] = pending_id
        await self.manager.message_sender.send_message(
            chat_id,
            f"✏️ {copy['manual_prompt']}",
        )
        # Cancel any existing timer for this pending_id
        if old := self.manager._wa_manual_timers.pop(pending_id, None):
            old.cancel()
        task = asyncio.create_task(
            self._manual_timeout_handler(pending_id, chat_id),
            name=f"wa-manual-timer-{pending_id}",
        )
        self.manager._wa_manual_timers[pending_id] = task

    async def ignore_message(self, chat_id: str, pending_id: str) -> None:
        """Ignore and remove a pending WhatsApp message."""
        self.manager._pending_wa.pop(pending_id, None)
        self._cancel_manual_timer(pending_id)
        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        await self.manager.message_sender.send_message(
            chat_id,
            f"✅ {copy['ignored']}",
            reply_markup=self.manager._default_keyboard(),
        )

    async def allow_sender(self, chat_id: str, pending_id: str) -> None:
        """Allow an unknown WhatsApp sender to send future messages."""
        pending = self.manager._pending_wa.get(pending_id)
        if not pending:
            await self.manager.message_sender.send_message(
                chat_id, "⚠️ Pending message not found (expired?)."
            )
            return
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        if not whatsapp_manager.register_known_sender(pending.from_number):
            await self.manager.message_sender.send_message(
                chat_id,
                copy["allow_failed"],
                reply_markup=self.manager._default_keyboard(),
            )
            return
        pending.is_known = True
        markup = {
            "inline_keyboard": [[
                {"text": "🤖 Gemini Draft", "callback_data": f"wa_gemini_{pending_id}"},
                {"text": f"✏️ {copy['manual']}", "callback_data": f"wa_manual_{pending_id}"},
                {"text": "❌ Ignore", "callback_data": f"wa_ignore_{pending_id}"},
            ]]
        }
        await self.manager.message_sender.send_message(
            chat_id,
            f"✅ {copy['allow_success'].format(number=pending.from_number)}",
            reply_markup=markup,
        )

    async def block_sender(self, chat_id: str, pending_id: str) -> None:
        """Block an unknown WhatsApp sender from sending future messages."""
        pending = self.manager._pending_wa.get(pending_id)
        if not pending:
            await self.manager.message_sender.send_message(
                chat_id, "⚠️ Pending message not found (expired?)."
            )
            return
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        if not whatsapp_manager.block_sender(pending.from_number):
            await self.manager.message_sender.send_message(
                chat_id,
                copy["block_failed"],
                reply_markup=self.manager._default_keyboard(),
            )
            return
        self.manager._pending_wa.pop(pending_id, None)
        self._cancel_manual_timer(pending_id)
        await self.manager.message_sender.send_message(
            chat_id,
            f"🚫 {copy['block_success'].format(number=pending.from_number)}",
            reply_markup=self.manager._default_keyboard(),
        )

    async def complete_manual_reply(
        self, chat_id: str, pending_id: str, text: str
    ) -> None:
        """Complete a manual reply workflow by sending the user's typed message."""
        pending = self.manager._pending_wa.get(pending_id)
        if not pending:
            await self.manager.message_sender.send_message(
                chat_id, "⚠️ Pending message not found (expired?)."
            )
            return
        if not await self.require_wa_reply_authorization(chat_id, pending):
            self._cancel_manual_timer(pending_id)
            self.manager._wa_manual_awaiting.pop(chat_id, None)
            return
        self._cancel_manual_timer(pending_id)
        self.manager._wa_manual_awaiting.pop(chat_id, None)
        self.manager._pending_wa.pop(pending_id, None)
        await self._send_wa_reply(chat_id, pending, text)

    async def _manual_timeout_handler(
        self, pending_id: str, chat_id: str
    ) -> None:
        """Background task — auto-cancels a manual WA reply after MANUAL_TIMEOUT."""
        try:
            await asyncio.sleep(MANUAL_TIMEOUT)
            if self.manager._wa_manual_awaiting.get(chat_id) == pending_id:
                self.manager._wa_manual_awaiting.pop(chat_id, None)
                self.manager._pending_wa.pop(pending_id, None)
                self.manager._wa_manual_timers.pop(pending_id, None)
                copy = self._wa_ui_copy(self._chat_language_style(chat_id))
                await self.manager.message_sender.send_message(
                    chat_id,
                    f"⏱️ {copy['manual_timeout']}",
                    reply_markup=self.manager._default_keyboard(),
                )
        except asyncio.CancelledError:
            pass

    def _cancel_manual_timer(self, pending_id: str) -> None:
        """Cancel the timeout timer for a pending manual reply."""
        if timer := self.manager._wa_manual_timers.pop(pending_id, None):
            timer.cancel()

    async def _send_wa_reply(
        self, chat_id: str, pending: PendingWAReply, reply_text: str
    ) -> None:
        """Send a reply to WhatsApp and notify the user of the result."""
        if not await self.require_wa_reply_authorization(chat_id, pending):
            return
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        copy = self._wa_ui_copy(self._chat_language_style(chat_id))
        ok = whatsapp_manager.reply_to_chat(pending.chat_id_wa, reply_text)
        self.manager._pending_wa.pop(pending.id, None)
        if ok:
            await self.manager.message_sender.send_message(
                chat_id,
                f"✅ {copy['reply_sent']}\n\n`{reply_text}`",
                reply_markup=self.manager._default_keyboard(),
            )
        else:
            await self.manager.message_sender.send_message(
                chat_id,
                f"❌ {copy['reply_failed']}",
                reply_markup=self.manager._default_keyboard(),
            )

    def _chat_language_style(self, chat_id: str) -> str:
        """Get the current language style for a chat."""
        return get_latest_conversation_style()

    @staticmethod
    def _detect_language_hint(text: str) -> str:
        """Detect and return a language hint for the given text."""
        style = detect_language_style(text)
        if style == BANGLISH:
            return "🇧🇩 Banglish"
        elif style == HINDILISH:
            return "🇮🇳 Hindilish"
        else:
            return "🇬🇧 English"

