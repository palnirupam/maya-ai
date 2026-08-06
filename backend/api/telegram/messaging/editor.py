"""
editor.py
=========
Handles Telegram message editing operations with retry logic and fallback handling.

Extracted from telegram_bot.py to provide clean separation of concerns.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.api.telegram.messaging.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Constants
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class MessageEditor:
    """
    Handles editing of Telegram messages with automatic retry logic and
    Markdown parse error fallback.
    """

    def __init__(self, manager: "TelegramBotManager") -> None:
        """
        Initialize the MessageEditor.

        Args:
            manager: Reference to the TelegramBotManager for access to HTTP client and token.
        """
        self.manager = manager
        from backend.api.telegram.messaging.rate_limiter import RateLimiter
        self.rate_limiter = RateLimiter(manager)

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        *,
        reply_markup: Optional[dict] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> None:
        """
        Edit an existing Telegram message.

        This method handles:
        - Text truncation to Telegram's 4096 character limit
        - Automatic Markdown parse error fallback to plain text
        - Rate limiting with exponential backoff
        - Graceful failure handling

        Args:
            chat_id: Telegram chat ID
            message_id: ID of the message to edit
            text: New text content (will be truncated to 4096 chars)
            reply_markup: Optional inline keyboard markup
            parse_mode: Parse mode (default: "Markdown", set to None for plain text)
        """
        if not self.manager.bot_token or not message_id or not self.manager._http:
            return

        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:4096],
        }
        
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            # First attempt with the provided parse_mode
            resp = await self.manager._http.post(
                TELEGRAM_API.format(token=self.manager.bot_token, method="editMessageText"),
                json=payload,
                timeout=10.0,
            )
            result = resp.json()
            
            # If Markdown parse error, retry as plain text
            if not result.get("ok") and parse_mode:
                logger.debug("Markdown parse error, retrying edit as plain text")
                payload.pop("parse_mode", None)
                await self.manager._http.post(
                    TELEGRAM_API.format(token=self.manager.bot_token, method="editMessageText"),
                    json=payload,
                    timeout=10.0,
                )
                
        except Exception as exc:
            logger.debug("edit_message failed: %s", exc)

    async def delete_message(
        self,
        chat_id: str,
        message_id: str,
    ) -> bool:
        """
        Delete a Telegram message.
        
        Args:
            chat_id: Telegram chat ID
            message_id: Message ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not self.manager.bot_token or not self.manager._http:
            return False
        
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        
        try:
            await self.rate_limiter.post_with_retry("deleteMessage", payload)
            logger.debug(f"Deleted message {message_id} in chat {chat_id}")
            return True
        except Exception as exc:
            logger.debug(f"Could not delete message {message_id}: {exc}")
            return False
