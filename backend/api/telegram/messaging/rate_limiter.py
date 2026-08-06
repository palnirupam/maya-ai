"""
rate_limiter.py
===============
Handles Telegram API rate limiting with exponential backoff and retry logic.

Extracted from telegram_bot.py to provide clean separation of concerns.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

# Constants
MAX_EDIT_RETRIES = 3
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class RateLimiter:
    """
    Handles Telegram API HTTP requests with rate limiting, exponential backoff,
    and automatic retry logic for 429 errors and Markdown parse failures.
    """

    def __init__(self, manager: "TelegramBotManager") -> None:
        """
        Initialize the RateLimiter.

        Args:
            manager: Reference to the TelegramBotManager for access to HTTP client and token.
        """
        self.manager = manager
        self._http: Optional[httpx.AsyncClient] = None
        self.bot_token: Optional[str] = None

    def _update_refs(self) -> None:
        """Update internal references from manager."""
        self._http = self.manager._http
        self.bot_token = self.manager.bot_token

    async def post_with_retry(
        self,
        method: str,
        payload: dict,
        *,
        max_retries: int = MAX_EDIT_RETRIES,
    ) -> None:
        """
        POST to Telegram API with exponential back-off on 429 Too Many Requests.

        This method handles:
        - 429 rate limiting with exponential backoff
        - Automatic Markdown parse error fallback to plain text
        - Connection failures with retry logic

        Args:
            method: Telegram API method name (e.g., "sendMessage", "editMessageText")
            payload: JSON payload to send
            max_retries: Maximum number of retry attempts (default: 3)
        """
        self._update_refs()
        if not self._http or not self.bot_token:
            return

        url = TELEGRAM_API.format(token=self.bot_token, method=method)
        delay = 1.0

        for attempt in range(max_retries):
            try:
                resp = await self._http.post(url, json=payload, timeout=10.0)
                
                # Handle 429 rate limiting
                if resp.status_code == 429:
                    retry_after = float(
                        resp.json().get("parameters", {}).get("retry_after", delay)
                    )
                    logger.warning(
                        "Telegram 429 — waiting %.1fs (attempt %d/%d)",
                        retry_after, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(retry_after)
                    delay = retry_after * 2
                    continue

                # For Markdown errors on sendMessage, retry as plain text
                result = resp.json()
                if not result.get("ok") and "parse_mode" in payload:
                    logger.debug("Markdown parse error, retrying as plain text")
                    payload = {**payload}
                    payload.pop("parse_mode", None)
                    continue

                # Success
                return

            except Exception as exc:
                logger.error("HTTP post failed (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(delay)
                delay *= 2

    async def post_with_retry_get_result(
        self,
        method: str,
        payload: dict,
        *,
        max_retries: int = MAX_EDIT_RETRIES,
    ) -> Optional[dict]:
        """
        POST to Telegram API and return the result data.

        Similar to post_with_retry but returns the result object for methods
        that need to extract data from the response (like message_id).

        Args:
            method: Telegram API method name
            payload: JSON payload to send
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            The "result" field from Telegram API response, or None on failure
        """
        self._update_refs()
        if not self._http or not self.bot_token:
            return None

        url = TELEGRAM_API.format(token=self.bot_token, method=method)
        delay = 1.0

        for attempt in range(max_retries):
            try:
                resp = await self._http.post(url, json=payload, timeout=10.0)
                
                # Handle 429 rate limiting
                if resp.status_code == 429:
                    retry_after = float(
                        resp.json().get("parameters", {}).get("retry_after", delay)
                    )
                    logger.warning(
                        "Telegram 429 — waiting %.1fs (attempt %d/%d)",
                        retry_after, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(retry_after)
                    delay = retry_after * 2
                    continue

                # Parse response
                data = resp.json()
                if data.get("ok"):
                    return data.get("result")
                else:
                    logger.error("Telegram API error: %s", data)
                    return None

            except Exception as exc:
                logger.error("HTTP post failed (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(delay)
                delay *= 2

        return None
