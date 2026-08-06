"""
lifecycle.py
============
Lifecycle management for Telegram bot - handles configuration loading,
start/stop/restart operations, and task management.

Extracted from telegram_bot.py for better modularity and maintainability.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import TYPE_CHECKING, Optional

import httpx

from backend.database.connection import SessionLocal
from backend.database.crypto import crypto_manager, KeyUnreadableError
from backend.database.models import UserPreferences

if TYPE_CHECKING:
    from backend.api.telegram_bot import TelegramBotManager

logger = logging.getLogger(__name__)


class LifecycleManager:
    """
    Manages the lifecycle of the Telegram bot including configuration loading,
    starting, stopping, and restarting operations.
    """

    def __init__(self, manager: "TelegramBotManager"):
        """
        Initialize the lifecycle manager.

        Args:
            manager: Reference to the parent TelegramBotManager instance
        """
        self.manager = manager

    def load_config(self) -> None:
        """
        Load / refresh config from the database. Thread-safe (no async).
        
        Loads:
        - TELEGRAM_BOT_ENABLED: Whether the bot is enabled
        - TELEGRAM_BOT_TOKEN: The bot authentication token
        - TELEGRAM_CHAT_ID: The authorized chat ID
        - TELEGRAM_PAIRING_CODE: 6-digit pairing code (generates if missing)
        
        All sensitive values are encrypted in the database using crypto_manager.
        """
        db = SessionLocal()
        try:
            def _get(key: str) -> Optional[str]:
                """Helper to get and decrypt a preference value."""
                pref = db.query(UserPreferences).filter(
                    UserPreferences.key == key
                ).first()
                if not pref or not pref.value:
                    return None
                try:
                    decrypted = crypto_manager.decrypt(pref.value, raise_on_failure=True)
                    return decrypted or pref.value
                except KeyUnreadableError as e:
                    logger.error(f"Failed to decrypt {key}: {e}")
                    return None

            def _set(key: str, value: str) -> None:
                """Helper to encrypt and store a preference value."""
                enc = crypto_manager.encrypt(value)
                pref = db.query(UserPreferences).filter(
                    UserPreferences.key == key
                ).first()
                if pref:
                    pref.value = enc
                else:
                    db.add(UserPreferences(key=key, value=enc))
                db.commit()

            # Load enabled flag
            enabled_val = _get("TELEGRAM_BOT_ENABLED")
            self.manager.enabled = enabled_val == "true"
            
            # Load bot credentials
            self.manager.bot_token = _get("TELEGRAM_BOT_TOKEN")
            self.manager.chat_id = _get("TELEGRAM_CHAT_ID")

            # Load or generate pairing code
            code = _get("TELEGRAM_PAIRING_CODE")
            if not code:
                # Use secrets for secure pairing code (6-digit number)
                code = str(secrets.randbelow(900000) + 100000)
                _set("TELEGRAM_PAIRING_CODE", code)
            self.manager.pairing_code = code

        finally:
            db.close()

    def start(self) -> None:
        """
        Start the bot (call from an asyncio context, after load_config).
        
        Creates:
        - HTTP client for Telegram API calls
        - Poll task for receiving messages
        - WhatsApp listener task for forwarding WhatsApp messages
        - WhatsApp cleanup task for removing old pending messages
        
        Does nothing if:
        - Bot is disabled
        - Bot token is missing
        - Bot is already running
        """
        self.load_config()
        
        if not (self.manager.enabled and self.manager.bot_token):
            logger.info("Telegram Bot disabled or missing token — skipping start.")
            return
            
        if self.manager.running:
            logger.warning("Telegram Bot already running — call restart() to reload.")
            return

        self.manager.running = True
        
        # Create persistent HTTP client for connection reuse
        self.manager._http = httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0))
        
        # Spawn background tasks
        self.manager._poll_task = asyncio.create_task(
            self.manager._poll_loop(),
            name="tg-poll"
        )
        self.manager._wa_listener_task = asyncio.create_task(
            self.manager._wa_listener_loop(),
            name="tg-wa-listener"
        )
        self.manager._wa_cleanup_task = asyncio.create_task(
            self.manager._wa_cleanup_loop(),
            name="tg-wa-cleanup"
        )
        
        logger.info("Telegram Bot started.")

    async def stop(self) -> None:
        """
        Gracefully stop all tasks and close the HTTP client.
        
        Cancels:
        - Poll task
        - WhatsApp listener task
        - WhatsApp cleanup task
        - All active command processing tasks
        - All WhatsApp manual reply timers
        
        Then closes the HTTP client and clears all state.
        """
        self.manager.running = False
        
        # Collect all tasks that need to be cancelled
        tasks = [
            t for t in [
                self.manager._poll_task,
                self.manager._wa_listener_task,
                self.manager._wa_cleanup_task,
                *self.manager._active_tasks.values(),
                *self.manager._wa_manual_timers.values(),
            ]
            if t and not t.done()
        ]
        
        # Cancel all tasks
        for t in tasks:
            t.cancel()
            
        # Wait for all tasks to complete cancellation
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Close HTTP client
        if self.manager._http:
            await self.manager._http.aclose()
            self.manager._http = None

        # Clear task references and state
        self.manager._poll_task = None
        self.manager._wa_listener_task = None
        self.manager._wa_cleanup_task = None
        self.manager._active_tasks.clear()
        self.manager._task_states.clear()
        self.manager._wa_manual_timers.clear()
        
        logger.info("Telegram Bot stopped.")

    async def restart(self) -> None:
        """
        Restart the bot by stopping it completely, then starting it again.
        
        Useful for:
        - Reloading configuration changes
        - Recovering from errors
        - Updating bot token or chat ID
        """
        await self.stop()
        self.start()
