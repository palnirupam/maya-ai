"""
command_handler.py
==================
Static command handlers for Telegram bot.

Extracts all non-dynamic command handling logic from telegram_bot.py
"""

import io
import logging
from typing import Optional

from backend.brain.language_style import (
    BANGLISH,
    ENGLISH,
    HINDILISH,
)
from backend.system.process_manager import process_manager
from backend.vision.capture.screen_capture import screen_capture

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles static Telegram commands (help, status, screenshot, etc.)"""

    def __init__(self, manager):
        """
        Initialize with reference to TelegramBotManager.
        
        Args:
            manager: TelegramBotManager instance for accessing bot state and methods
        """
        self.manager = manager

    async def handle_static_command(self, chat_id: str, text_lower: str) -> bool:
        """
        Route and handle static commands.
        
        Args:
            chat_id: Telegram chat ID
            text_lower: Lowercased message text
            
        Returns:
            True if command was handled, False otherwise
        """
        # Help command
        if text_lower in {"/start", "/help", "❓ help & guide"}:
            await self.send_help(chat_id)
            return True
            
        # Unpair command
        if text_lower in {"/reset", "👤 unpair bot"}:
            await self.unpair(chat_id)
            return True
            
        # Status command
        if text_lower in {"/status", "📊 check status"}:
            await self.send_status(chat_id)
            return True
            
        # Screenshot command
        if text_lower in {"/screenshot", "📸 get screenshot"}:
            await self.send_screenshot(chat_id, "Here is your current desktop screen:")
            return True
            
        # WhatsApp link guide
        if text_lower in {"/whatsapp_qr", "🟢 whatsapp qr", "🔑 whatsapp link"}:
            await self.send_wa_link_guide(chat_id)
            return True
            
        # Microphone lock
        if text_lower in {"/lock", "🔒 mic lock", "lock mic", "sleep mode on",
                          "mic lock koro", "lock koro", "ঘুমাও", "lock"}:
            await self.lock_microphone(chat_id)
            return True
            
        # Microphone unlock
        if text_lower in {"/unlock", "🔓 mic unlock", "unlock mic", "sleep mode off",
                          "mic unlock koro", "unlock koro", "জাগো", "unlock"}:
            await self.unlock_microphone(chat_id)
            return True
        
        # Command not handled
        return False

    async def send_help(self, chat_id: str) -> None:
        """Send help message with available commands."""
        copy = self._get_ui_copy(chat_id)
        await self.manager._send_message(
            chat_id,
            "👋 *Maya AI — Advanced Control*\n\n"
            "🖥️ *Browser:* `\"google.com e jao\"` / `\"youtube khol\"`\n"
            "🎵 *Media:* `\"spotify play\"` / `\"next song\"` / `\"volume 50%\"`\n"
            "💬 *WhatsApp:* `\"[Name] ke message koro [Text]\"`\n"
            "🚀 *Apps:* `\"VS Code khol\"` / `\"Chrome open\"`\n"
            f"{copy['help_status_line']}\n"
            f"{copy['help_screenshot_line']}\n",
            reply_markup=self.manager._default_keyboard(),
        )

    async def send_status(self, chat_id: str) -> None:
        """Send system status (CPU, RAM, active window, mic status)."""
        try:
            from backend.tools.desktop.advanced.system_tools import get_system_stats
            import pygetwindow as gw
            from backend.api.main import get_active_listener
            
            stats = get_system_stats()
            active = gw.getActiveWindow()
            title = active.title if active else "None"
            listener = get_active_listener()
            mic_status = (
                "🔒 Locked (Sleep Mode)" 
                if (listener and listener.is_locked) 
                else "🎙️ Active (Listening)"
            )
            msg = (
                "📊 *System Status:*\n\n"
                f"🖥️ *Active Window:* `{title}`\n"
                f"🎙️ *Microphone:* {mic_status}\n"
                f"🔋 *Resources:* {stats}"
            )
        except Exception as exc:
            msg = f"❌ Stats error: {exc}"
            
        await self.manager._send_message(
            chat_id, 
            msg, 
            reply_markup=self.manager._default_keyboard()
        )

    async def send_screenshot(self, chat_id: str, caption: str = "📸 Screenshot") -> None:
        """
        Capture and send desktop screenshot.
        
        Args:
            chat_id: Telegram chat ID
            caption: Caption for the screenshot
        """
        if not self.manager.bot_token or not self.manager._http:
            return
            
        img, _ = screen_capture.capture_as_pil()
        if not img:
            await self.manager._send_message(
                chat_id,
                "⚠️ *Screenshot Blocked* — sensitive app (bank/password manager) open.",
                reply_markup=self.manager._default_keyboard(),
            )
            return
            
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        buf.seek(0)
        
        try:
            import json
            await self.manager._http.post(
                f"https://api.telegram.org/bot{self.manager.bot_token}/sendPhoto",
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "reply_markup": json.dumps(self.manager._default_keyboard()),
                    "parse_mode": "Markdown",
                },
                files={"photo": ("screenshot.jpg", buf.read(), "image/jpeg")},
                timeout=20.0,
            )
        except Exception as exc:
            logger.error("send_screenshot failed: %s", exc)

    async def send_wa_link_guide(self, chat_id: str) -> None:
        """Send WhatsApp linking instructions."""
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        
        copy = self._get_ui_copy(chat_id)
        if whatsapp_manager.get_status().get("status") == "connected":
            await self.manager._send_message(
                chat_id, 
                copy["wa_connected"],
                reply_markup=self.manager._default_keyboard(),
            )
        else:
            await self.manager._send_message(
                chat_id,
                copy["wa_link_guide"],
                reply_markup=self.manager._default_keyboard(),
            )

    async def lock_microphone(self, chat_id: str) -> None:
        """Lock microphone (Sleep Mode)."""
        try:
            from backend.api.main import get_active_listener
            
            listener = get_active_listener()
            copy = self._get_ui_copy(chat_id)
            
            if listener is None:
                await self.manager._send_message(
                    chat_id,
                    copy["mic_no_engine"],
                    reply_markup=self.manager._default_keyboard(),
                )
                return
                
            if listener.is_manually_locked:
                await self.manager._send_message(
                    chat_id,
                    copy["mic_already_locked"],
                    reply_markup=self.manager._default_keyboard(),
                )
                return
                
            listener.lock()
            await self.manager._send_message(
                chat_id,
                copy["mic_locked"],
                reply_markup=self.manager._default_keyboard(),
            )
            logger.info("[CommandHandler] Microphone locked via Telegram by chat_id=%s", chat_id)
            
        except Exception as exc:
            logger.error("Lock microphone error: %s", exc, exc_info=True)
            await self.manager._send_message(
                chat_id, 
                f"❌ Lock error: {exc}",
                reply_markup=self.manager._default_keyboard()
            )

    async def unlock_microphone(self, chat_id: str) -> None:
        """Unlock microphone (Wake from Sleep Mode)."""
        try:
            from backend.api.main import get_active_listener
            
            listener = get_active_listener()
            copy = self._get_ui_copy(chat_id)
            
            if listener is None:
                await self.manager._send_message(
                    chat_id,
                    copy["mic_no_engine"],
                    reply_markup=self.manager._default_keyboard(),
                )
                return
                
            if not listener.is_manually_locked:
                await self.manager._send_message(
                    chat_id,
                    copy["mic_already_unlocked"],
                    reply_markup=self.manager._default_keyboard(),
                )
                return
                
            listener.unlock()
            await self.manager._send_message(
                chat_id,
                copy["mic_unlocked"],
                reply_markup=self.manager._default_keyboard(),
            )
            logger.info("[CommandHandler] Microphone unlocked via Telegram by chat_id=%s", chat_id)
            
        except Exception as exc:
            logger.error("Unlock microphone error: %s", exc, exc_info=True)
            await self.manager._send_message(
                chat_id, 
                f"❌ Unlock error: {exc}",
                reply_markup=self.manager._default_keyboard()
            )

    async def emergency_stop(self, chat_id: str) -> None:
        """
        Trigger emergency stop - cancels active task and kills all managed processes.
        """
        # 1. Cancel the specific active task in the telegram bot stream
        task = self.manager._active_tasks.get(chat_id)
        if task and not task.done():
            task.cancel()
            self.manager._active_tasks.pop(chat_id, None)
            
        # 2. Trigger the Deep Emergency Stop for all OS processes and background tasks
        await self.manager._send_message(
            chat_id, 
            "🛑 *Emergency Stop Triggered!* Canceling tasks and forcefully terminating process trees..."
        )
        
        try:
            stats = await process_manager.emergency_stop()
            tasks_canceled = stats.get("tasks_canceled", 0)
            pids_killed = stats.get("pids_killed", 0)
            
            await self.manager._send_message(
                chat_id,
                f"✅ *System Halted.*\n- Tasks canceled: {tasks_canceled}\n- Processes force-killed: {pids_killed}",
                reply_markup=self.manager._default_keyboard(),
            )
        except Exception as e:
            logger.error(f"Error during deep emergency stop: {e}")
            await self.manager._send_message(
                chat_id, 
                "⚠️ Error during deep emergency stop."
            )

    async def unpair(self, chat_id: str) -> None:
        """Unpair bot (delete configuration)."""
        from backend.database.connection import SessionLocal
        from backend.database.models import UserPreferences
        
        db = SessionLocal()
        try:
            if pref := db.query(UserPreferences).filter(
                UserPreferences.key == "TELEGRAM_CHAT_ID"
            ).first():
                db.delete(pref)
                db.commit()
            self.manager.chat_id = None
        finally:
            db.close()
            
        copy = self._get_ui_copy(chat_id)
        await self.manager._send_message(
            chat_id,
            copy["unpaired"],
        )

    def _get_ui_copy(self, chat_id: str) -> dict:
        """
        Get localized UI copy based on chat's language style.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            Dictionary of localized messages
        """
        style = self.manager._chat_language_styles.get(chat_id, ENGLISH)
        
        if style == BANGLISH:
            return {
                "help_status_line": "📊 *Status:* `/status` check koro",
                "help_screenshot_line": "📸 *Screenshot:* `/screenshot` pathao",
                "wa_connected": "🟢 *WhatsApp already connected!*",
                "wa_link_guide": "🔑 *WhatsApp Link Guide:*\n\n1. Send: `/whatsapp_pair [phone]`\n   Example: `/whatsapp_pair 9876543210`\n2. Bot 8-digit pairing code dibe.\n3. WhatsApp → Settings → Linked Devices → Link a Device\n4. Tap *Link with phone number instead* → code enter korun.",
                "mic_no_engine": "⚠️ *Voice engine chalu nei.* Maya restart koro prothome.",
                "mic_already_locked": "🔒 *Microphone already locked!*\n\nUnlock korte `/unlock` pathao.",
                "mic_locked": "🔒 *Microphone Locked!*\n\nMaya ekhon ghumiye porechhe. 😴\nTomar ghore keyu kotha bolleo she shunbe na.\n\nFire ele `/unlock` diye jagiye dao.",
                "mic_already_unlocked": "🔓 *Microphone already unlocked!*\n\nMaya sokriyobhabe shunchhe.",
                "mic_unlocked": "🔓 *Microphone Unlocked!*\n\nMaya ekhon jege uthechhe! 👋\nLaptop-er samne kotha bollei she shunbe.",
                "unpaired": "🔴 *Unpaired.*\n\nJekonosamay `/pair [passcode]` diye notun account pair korun.",
            }
            
        if style == HINDILISH:
            return {
                "help_status_line": "📊 *Status:* `/status` check karo",
                "help_screenshot_line": "📸 *Screenshot:* `/screenshot` bhejo",
                "wa_connected": "🟢 *WhatsApp already connected!*",
                "wa_link_guide": "🔑 *WhatsApp Link Guide:*\n\n1. Send: `/whatsapp_pair [phone]`\n   Example: `/whatsapp_pair 9876543210`\n2. Bot 8-digit pairing code dega.\n3. WhatsApp → Settings → Linked Devices → Link a Device\n4. Tap *Link with phone number instead* → code enter karein.",
                "mic_no_engine": "⚠️ *Voice engine chalu nahi hai.* Pehle Maya restart karo.",
                "mic_already_locked": "🔒 *Microphone already locked!*\n\nUnlock karne ke liye `/unlock` bhejo.",
                "mic_locked": "🔒 *Microphone Locked!*\n\nMaya ab so gayi hai. 😴\nAapke kamre me koi baat kare to bhi wo nahi sunegi.\n\nWapas aakar `/unlock` se jaga do.",
                "mic_already_unlocked": "🔓 *Microphone already unlocked!*\n\nMaya actively sun rahi hai.",
                "mic_unlocked": "🔓 *Microphone Unlocked!*\n\nMaya ab jaag gayi hai! 👋\nLaptop ke samne bolte hi wo sunegi.",
                "unpaired": "🔴 *Unpaired.*\n\nKabhi bhi `/pair [passcode]` se naya account pair karein.",
            }
            
        # English (default)
        return {
            "help_status_line": "📊 *Status:* Check with `/status`",
            "help_screenshot_line": "📸 *Screenshot:* Send `/screenshot`",
            "wa_connected": "🟢 *WhatsApp already connected!*",
            "wa_link_guide": "🔑 *WhatsApp Link Guide:*\n\n1. Send: `/whatsapp_pair [phone]`\n   Example: `/whatsapp_pair 9876543210`\n2. Bot will give you an 8-digit pairing code.\n3. WhatsApp → Settings → Linked Devices → Link a Device\n4. Tap *Link with phone number instead* → enter code.",
            "mic_no_engine": "⚠️ *Voice engine not running.* Please restart Maya first.",
            "mic_already_locked": "🔒 *Microphone already locked!*\n\nSend `/unlock` to unlock.",
            "mic_locked": "🔒 *Microphone Locked!*\n\nMaya is now sleeping. 😴\nEven if someone talks in your room, she won't listen.\n\nSend `/unlock` to wake her up.",
            "mic_already_unlocked": "🔓 *Microphone already unlocked!*\n\nMaya is actively listening.",
            "mic_unlocked": "🔓 *Microphone Unlocked!*\n\nMaya is now awake! 👋\nShe will listen when you speak near the laptop.",
            "unpaired": "🔴 *Unpaired.*\n\nPair a new account anytime with `/pair [passcode]`.",
        }
