"""
sender.py
=========
Handles sending messages through Telegram API.

Extracted from telegram_bot.py to provide clean separation of messaging concerns.
Uses RateLimiter for all HTTP operations with built-in retry logic.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from .rate_limiter import RateLimiter

if TYPE_CHECKING:
    from backend.api.telegram_bot import TelegramBotManager

logger = logging.getLogger(__name__)


class MessageSender:
    """
    Handles sending messages through Telegram API with automatic fallback
    on Markdown parse errors and rate limiting support.
    """

    def __init__(self, manager: "TelegramBotManager") -> None:
        """
        Initialize the MessageSender.

        Args:
            manager: Reference to the TelegramBotManager for access to configuration.
        """
        self.manager = manager
        self.rate_limiter = RateLimiter(manager)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: Optional[dict] = None,
        parse_mode: str = "Markdown",
    ) -> None:
        """
        Send a message to a Telegram chat.

        Automatically handles:
        - Message length truncation (4096 chars)
        - Markdown parse errors with fallback to plain text
        - Rate limiting with exponential backoff
        - Connection failures with retry logic

        Args:
            chat_id: Telegram chat ID to send message to
            text: Message text content
            reply_markup: Optional keyboard markup (reply keyboard or inline keyboard)
            parse_mode: Parse mode for message formatting (default: "Markdown")
        """
        if not self.manager.bot_token or not self.manager._http:
            return

        # Truncate message to Telegram's 4096 character limit
        payload: dict = {
            "chat_id":    chat_id,
            "text":       text[:4096],
            "parse_mode": parse_mode,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        await self.rate_limiter.post_with_retry("sendMessage", payload)

    async def send_message_get_id(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: Optional[str] = "Markdown",
    ) -> Optional[str]:
        """
        Send a message and return its message_id.

        This is useful for operations that need to reference the sent message
        later (e.g., editing or deleting it).

        Args:
            chat_id: Telegram chat ID to send message to
            text: Message text content
            parse_mode: Parse mode for message formatting (default: "Markdown")

        Returns:
            The message_id as a string if successful, None otherwise
        """
        if not self.manager.bot_token or not self.manager._http:
            return None

        # Truncate message to Telegram's 4096 character limit
        payload: dict = {"chat_id": chat_id, "text": text[:4096]}
        
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            result = await self.rate_limiter.post_with_retry_get_result(
                "sendMessage", payload
            )
            
            if result and "message_id" in result:
                return str(result["message_id"])
                
        except Exception as exc:
            logger.error("send_message_get_id failed: %s", exc)

        return None
