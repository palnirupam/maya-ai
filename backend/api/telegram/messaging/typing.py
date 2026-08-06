"""
typing.py
=========
Handles Telegram typing indicators, callback query responses, and screenshot sending.

Extracted from telegram_bot.py to provide clean separation of concerns.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.api.telegram.telegram_bot import TelegramBotManager

logger = logging.getLogger(__name__)

# Constants
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TypingIndicator:
    """
    Handles Telegram chat actions (typing indicator), callback query answers,
    and screenshot sending operations.
    """

    def __init__(self, manager: "TelegramBotManager") -> None:
        """
        Initialize the TypingIndicator.

        Args:
            manager: Reference to the TelegramBotManager for access to HTTP client and token.
        """
        self.manager = manager

    async def send_typing(self, chat_id: str) -> None:
        """
        Send a "typing..." indicator to the chat.

        This shows the user that the bot is processing their request.
        The indicator automatically disappears after ~5 seconds or when a message is sent.

        Args:
            chat_id: Telegram chat ID
        """
        if not self.manager.bot_token or not self.manager._http:
            return

        try:
            await self.manager._http.post(
                TELEGRAM_API.format(token=self.manager.bot_token, method="sendChatAction"),
                json={"chat_id": chat_id, "action": "typing"},
                timeout=5.0,
            )
        except Exception:
            # Typing indicator failure is non-critical, silently ignore
            pass

    async def answer_callback(self, callback_query_id: Optional[str]) -> None:
        """
        Acknowledge a callback query from an inline keyboard button.

        This removes the loading state from the button and prevents
        "query timed out" errors on the client side.

        Args:
            callback_query_id: The callback query ID to acknowledge
        """
        if not callback_query_id or not self.manager.bot_token or not self.manager._http:
            return

        try:
            await self.manager._http.post(
                TELEGRAM_API.format(token=self.manager.bot_token, method="answerCallbackQuery"),
                json={"callback_query_id": callback_query_id},
                timeout=5.0,
            )
        except Exception:
            # Callback answer failure is non-critical, silently ignore
            pass

    async def send_screenshot(self, chat_id: str, caption: str) -> None:
        """
        Capture and send a screenshot to the Telegram chat.

        This method:
        - Captures the current desktop screen using screen_capture
        - Blocks screenshot if sensitive apps (bank/password manager) are open
        - Sends the image as a JPEG with the provided caption
        - Includes the default keyboard in the reply

        Args:
            chat_id: Telegram chat ID
            caption: Caption text for the screenshot
        """
        if not self.manager.bot_token or not self.manager._http:
            return

        # Import screen_capture here to avoid circular dependencies
        from backend.vision.capture.screen_capture import screen_capture

        img, _ = screen_capture.capture_as_pil()
        if not img:
            # Screenshot blocked due to sensitive app
            await self._send_blocked_message(chat_id)
            return

        # Convert PIL image to JPEG bytes
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        buf.seek(0)

        try:
            await self.manager._http.post(
                TELEGRAM_API.format(token=self.manager.bot_token, method="sendPhoto"),
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "reply_markup": json.dumps(self._default_keyboard()),
                    "parse_mode": "Markdown",
                },
                files={"photo": ("screenshot.jpg", buf.read(), "image/jpeg")},
                timeout=20.0,
            )
        except Exception as exc:
            logger.error("send_screenshot failed: %s", exc)

    async def _send_blocked_message(self, chat_id: str) -> None:
        """
        Send a message indicating that screenshot was blocked.

        Args:
            chat_id: Telegram chat ID
        """
        # Use the manager's send_message method to avoid duplication
        if hasattr(self.manager, '_send_message'):
            await self.manager._send_message(
                chat_id,
                "⚠️ *Screenshot Blocked* — sensitive app (bank/password manager) open.",
                reply_markup=self._default_keyboard(),
            )

    def _default_keyboard(self) -> dict:
        """
        Get the default keyboard markup from the manager.

        Returns:
            Default keyboard markup dictionary
        """
        if hasattr(self.manager, '_default_keyboard'):
            return self.manager._default_keyboard()
        return {"keyboard": [], "resize_keyboard": True}
