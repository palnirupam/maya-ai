import os
import asyncio
import logging
import httpx
import random
import io
import json
import subprocess
from typing import Optional
from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences
from backend.database.crypto import crypto_manager
from backend.brain.orchestrator import orchestrator
from backend.vision.capture.screen_capture import screen_capture

logger = logging.getLogger(__name__)

class TelegramBotManager:
    def __init__(self):
        self.polling_task: Optional[asyncio.Task] = None
        self.bot_token = None
        self.chat_id = None
        self.pairing_code = None
        self.enabled = False
        self.running = False
        self._pending_dangerous_cmd = None
        self.active_tasks = {}

    def load_config(self):
        db = SessionLocal()
        try:
            # 1. Enabled
            pref_enabled = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_ENABLED").first()
            self.enabled = False
            if pref_enabled and pref_enabled.value:
                decrypted = crypto_manager.decrypt(pref_enabled.value)
                val = decrypted if (decrypted or not pref_enabled.value) else pref_enabled.value
                self.enabled = (val == "true")

            # 2. Token
            pref_token = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_BOT_TOKEN").first()
            if pref_token and pref_token.value:
                decrypted = crypto_manager.decrypt(pref_token.value)
                self.bot_token = decrypted if (decrypted or not pref_token.value) else pref_token.value
            else:
                self.bot_token = None

            # 3. Chat ID
            pref_chat = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_CHAT_ID").first()
            if pref_chat and pref_chat.value:
                decrypted = crypto_manager.decrypt(pref_chat.value)
                self.chat_id = decrypted if (decrypted or not pref_chat.value) else pref_chat.value
            else:
                self.chat_id = None

            # 4. Pairing Code
            pref_code = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_PAIRING_CODE").first()
            if not pref_code or not pref_code.value:
                code = str(random.randint(100000, 999999))
                enc_code = crypto_manager.encrypt(code)
                if pref_code:
                    pref_code.value = enc_code
                else:
                    db.add(UserPreferences(key="TELEGRAM_PAIRING_CODE", value=enc_code))
                db.commit()
                self.pairing_code = code
            else:
                decrypted = crypto_manager.decrypt(pref_code.value)
                self.pairing_code = decrypted if (decrypted or not pref_code.value) else pref_code.value
        finally:
            db.close()

    def start(self):
        self.load_config()
        if self.enabled and self.bot_token:
            if not self.polling_task or self.polling_task.done():
                self.running = True
                self.polling_task = asyncio.create_task(self._poll_loop())
                logger.info("Telegram Bot service started.")
        else:
            logger.info("Telegram Bot is disabled or missing token.")

    def stop(self):
        self.running = False
        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()
            logger.info("Telegram Bot service stopped.")
        self.polling_task = None

    def restart(self):
        self.stop()
        self.start()

    async def _poll_loop(self):
        offset = None
        while self.running:
            try:
                if not self.bot_token:
                    await asyncio.sleep(5.0)
                    continue

                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {"timeout": 20}
                if offset:
                    params["offset"] = offset

                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, params=params, timeout=25.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        updates = data.get("result", [])
                        for update in updates:
                            update_id = update["update_id"]
                            offset = update_id + 1
                            
                            message = update.get("message")
                            callback_query = update.get("callback_query")
                            
                            if callback_query:
                                asyncio.create_task(self._handle_callback_query(callback_query))
                            elif message:
                                asyncio.create_task(self._handle_message(message))
                    elif resp.status_code == 401:
                        logger.error("Telegram Bot Token is unauthorized/invalid.")
                        await asyncio.sleep(10.0)
                    elif resp.status_code == 409:
                        logger.warning("Telegram Bot API returned status 409 (Conflict). Proactively cleaning duplicate processes...")
                        self._clean_duplicate_processes()
                        await asyncio.sleep(5.0)
                    else:
                        logger.warning(f"Telegram Bot API returned status {resp.status_code}")
                        await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Telegram polling loop: {e}")
                await asyncio.sleep(5.0)

    async def _handle_callback_query(self, callback_query: dict):
        """Handle inline keyboard button presses (Yes/No confirmations)."""
        cq_id = callback_query.get("id")
        data = callback_query.get("data", "")
        chat_id = str(callback_query["message"]["chat"]["id"])
        
        # Answer the callback to remove "loading" spinner on the button
        if self.bot_token and cq_id:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery",
                        json={"callback_query_id": cq_id},
                        timeout=5.0
                    )
            except Exception:
                pass

        if data == "confirm_shutdown":
            if self._pending_dangerous_cmd and self._pending_dangerous_cmd.get("chat_id") == chat_id:
                original_text = self._pending_dangerous_cmd["text"]
                self._pending_dangerous_cmd = None
                await self._send_message(chat_id, "⚙️ *ঠিক আছে, execute করছি...*")
                session_id = f"telegram_{chat_id}"
                full_response = ""
                try:
                    async for chunk in orchestrator.process_user_input_stream(session_id, original_text):
                        if isinstance(chunk, dict):
                            continue
                        full_response += chunk
                    if full_response.strip():
                        await self._send_message(chat_id, full_response, reply_markup=self._get_default_keyboard())
                    else:
                        await self._send_message(chat_id, "✅ Done.", reply_markup=self._get_default_keyboard())
                except Exception as e:
                    await self._send_message(chat_id, f"❌ Error: {e}", reply_markup=self._get_default_keyboard())
            else:
                await self._send_message(chat_id, "⚠️ কোনো pending command নেই।", reply_markup=self._get_default_keyboard())

        elif data == "cancel_shutdown":
            self._pending_dangerous_cmd = None
            await self._send_message(chat_id, "✅ *বাতিল করা হয়েছে।* Laptop বন্ধ হয়নি।", reply_markup=self._get_default_keyboard())

    async def _handle_message(self, message: dict):
        chat = message["chat"]
        chat_id = str(chat["id"])
        text = message.get("text", "").strip()
        
        if not text:
            return

        # Check pairing status
        if not self.chat_id:
            if text.startswith("/pair"):
                parts = text.split(maxsplit=1)
                if len(parts) == 2 and parts[1].strip() == self.pairing_code:
                    db = SessionLocal()
                    try:
                        enc_chat_id = crypto_manager.encrypt(chat_id)
                        pref = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_CHAT_ID").first()
                        if pref:
                            pref.value = enc_chat_id
                        else:
                            db.add(UserPreferences(key="TELEGRAM_CHAT_ID", value=enc_chat_id))
                        db.commit()
                        self.chat_id = chat_id
                    finally:
                        db.close()
                    await self._send_message(chat_id, "🟢 *Pairing Successful!*\n\nYou are now authorized to command Maya AI from this Telegram account. Type any command (e.g. \"google.com e jao\" or \"/screenshot\") to begin.")
                else:
                    await self._send_message(chat_id, f"❌ *Incorrect passcode.*\n\nPlease use: `/pair [passcode]` where `[passcode]` is the 6-digit code shown in the Telegram settings of your Maya AI desktop app.")
            else:
                await self._send_message(chat_id, f"👋 *Hello! I am Maya AI.*\n\nTo pair this Telegram account with your desktop copilot, please send:\n`/pair {self.pairing_code}`\n\n*(You can see this pairing passcode on the Telegram tab in Settings on your desktop).*")
            return

        # Paired, verify sender
        if chat_id != self.chat_id:
            await self._send_message(chat_id, "❌ *Unauthorized Access.*\n\nThis Maya AI instance is already paired with another user's Telegram account.")
            return

        # Handle built-in commands and reply button taps
        text_lower = text.lower()
        
        # WhatsApp pairing code generator (Link with phone number)
        if text_lower.startswith("/whatsapp_pair") or "pair whatsapp" in text_lower or "whatsapp pair" in text_lower:
            # Extract only the digits from the entire text after removing command keywords
            clean_text = text
            for kw in ["/whatsapp_pair", "pair whatsapp", "whatsapp pair"]:
                if kw in clean_text.lower():
                    idx = clean_text.lower().find(kw)
                    clean_text = clean_text[:idx] + clean_text[idx + len(kw):]
            
            phone = "".join(c for c in clean_text if c.isdigit())
            if phone:
                if phone.startswith("00"):
                    phone = phone[2:]
                elif phone.startswith("0"):
                    phone = phone[1:]
                
                if len(phone) == 10:
                    phone = "91" + phone
            
            if not phone or len(phone) < 10:
                await self._send_message(chat_id, "❌ *Please provide a valid phone number.*\n\n*Usage:* `/whatsapp_pair [phone_number]`\nExample: `/whatsapp_pair 919876543210` or `/whatsapp_pair 9876543210`", reply_markup=self._get_default_keyboard())
                return
                
            await self._send_message(chat_id, f"⏳ *Requesting 8-digit pairing code for {phone} from WhatsApp...*", reply_markup=self._get_default_keyboard())
            
            from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
            code = whatsapp_manager.get_pairing_code(phone)
            
            if code:
                success_msg = (
                    "🔑 *WhatsApp Pairing Code:* `{}`\n\n"
                    "👉 *How to pair on your phone:*\n"
                    "1. Open **WhatsApp** on your phone.\n"
                    "2. Go to **Settings** -> **Linked Devices** -> tap **Link a Device**.\n"
                    "3. Tap **Link with phone number instead** at the bottom.\n"
                    "4. Enter the 8-digit pairing code above: `{}`\n\n"
                    "*(This code is stable and does not expire quickly!)*"
                ).format(code, code)
                await self._send_message(chat_id, success_msg, reply_markup=self._get_default_keyboard())
            else:
                await self._send_message(chat_id, "❌ *Failed to generate pairing code.*\n\nPlease check if your WhatsApp background service is active or try again in a few seconds.", reply_markup=self._get_default_keyboard())
            return

        # Route button taps or commands
        if text_lower in ["/start", "/help", "❓ help & guide"]:
            help_msg = (
                "👋 *Welcome to Maya AI Advanced Control Menu!*\n\n"
                "Use the interactive buttons below or type any command to control your laptop:\n\n"
                "🖥️ *Desktop & Browser Actions:*\n"
                "• `\"google.com e jao\"` — Browse any website.\n"
                "• `\"spotify play\"` / `\"next song\"` — Control media playback.\n"
                "• `\"volume 50%\"` / `\"mute\"` — Manage sound settings.\n\n"
                "💬 *WhatsApp Messenger:*\n"
                "• `\"save contact [Name] number [Phone]\"` — Add a contact.\n"
                "• `\"[Name] ke message koro [Message]\"` — Send a text instantly in the background.\n\n"
                "🚀 *Quick App Launcher:*\n"
                "• `\"VS Code khol\"` / `\"Chrome open kor\"` — Launch any desktop application.\n\n"
                "📊 *Utility & Settings:*\n"
                "• Tap *Check Status* to view resource usage and active window.\n"
                "• Tap *Get Screenshot* to see what is currently on your screen."
            )
            await self._send_message(chat_id, help_msg, reply_markup=self._get_default_keyboard())
            return
            
        if text_lower in ["/reset", "👤 unpair bot"]:
            db = SessionLocal()
            try:
                pref = db.query(UserPreferences).filter(UserPreferences.key == "TELEGRAM_CHAT_ID").first()
                if pref:
                    db.delete(pref)
                    db.commit()
                self.chat_id = None
            finally:
                db.close()
            # Send message without keyboard to reset interface
            await self._send_message(chat_id, "🔴 *Unpaired Successfully.*\n\nYou can pair a new account anytime by sending `/pair [passcode]`.")
            return
            
        if text_lower in ["/status", "📊 check status"]:
            from backend.tools.desktop.advanced.system_tools import get_system_stats
            import pygetwindow as gw
            try:
                stats = get_system_stats()
                active = gw.getActiveWindow()
                title = active.title if active else "None"
                status_msg = (
                    "📊 *Maya AI System Status:*\n\n"
                    f"🖥️ *Active Window:* `{title}`\n"
                    f"🔋 *Resources:* {stats}"
                )
            except Exception as e:
                status_msg = f"Failed to retrieve stats: {e}"
            await self._send_message(chat_id, status_msg, reply_markup=self._get_default_keyboard())
            return
            
        if text_lower in ["/screenshot", "📸 get screenshot"]:
            await self._send_screenshot(chat_id, "Here is your current desktop screen:")
            return
            
        if text_lower in ["/whatsapp_qr", "🟢 whatsapp qr", "🔑 whatsapp link"]:
            from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
            status = whatsapp_manager.get_status()
            
            if status.get("status") == "connected":
                await self._send_message(chat_id, "🟢 *WhatsApp is already connected!*", reply_markup=self._get_default_keyboard())
            else:
                pair_instructions = (
                    "🔑 *WhatsApp Link Guide (No QR Code Needed):*\n\n"
                    "To pair Maya AI with your WhatsApp account instantly:\n\n"
                    "1. Send your 10-digit phone number using the pair command:\n"
                    "   `/whatsapp_pair [phone_number]`\n"
                    "   *(Example:* `/whatsapp_pair 9876543210`*)*\n\n"
                    "2. The bot will immediately reply with an **8-digit pairing code**.\n"
                    "3. Open **WhatsApp** on your phone -> go to **Settings** -> **Linked Devices** -> tap **Link a Device**.\n"
                    "4. Tap **'Link with phone number instead'** at the bottom and enter the 8-digit code!"
                )
                await self._send_message(chat_id, pair_instructions, reply_markup=self._get_default_keyboard())
            return
            
        # ⚠️ DANGEROUS COMMAND DETECTION - require confirmation before executing
        DANGEROUS_KEYWORDS = [
            # Shutdown/restart
            "shutdown", "shut down", "restart", "reboot", "turn off",
            # Bengali equivalents
            "shut", "bondho", "বন্ধ", "শাটডাউন", "রিস্টার্ট",
            # Format/delete
            "format", "delete all", "wipe",
        ]
        SHUTDOWN_CONFIRM_KEYWORDS = ["shutdown", "shut down", "turn off", "bondho koro laptop", "laptop bondho", "shut", "শাটডাউন", "বন্ধ করো ল্যাপটপ"]
        
        is_dangerous_shutdown = any(kw in text_lower for kw in SHUTDOWN_CONFIRM_KEYWORDS) and any(
            w in text_lower for w in ["laptop", "pc", "computer", "system", "sob", "সব", "ল্যাপটপ"]
        )
        
        if is_dangerous_shutdown:
            # Store the pending command
            self._pending_dangerous_cmd = {"chat_id": chat_id, "text": text}
            confirm_markup = {
                "inline_keyboard": [[
                    {"text": "✅ হ্যাঁ, বন্ধ করো", "callback_data": "confirm_shutdown"},
                    {"text": "❌ না, বাতিল", "callback_data": "cancel_shutdown"}
                ]]
            }
            await self._send_message(
                chat_id,
                "⚠️ *Dangerous Command Detected!*\n\n"
                f"তুমি বলেছ: `{text}`\n\n"
                "এটা laptop shutdown করে দেবে। সত্যিই করবো?\n\n"
                "👇 নিচের বোতাম চাপো:",
                reply_markup=confirm_markup
            )
            return

        # Emergency STOP detection
        if text.lower() in ["stop", "halt", "panic", "🛑 emergency stop", "thamo", "থামো", "থাম"]:
            active_task = self.active_tasks.get(chat_id)
            if active_task and not active_task.done():
                active_task.cancel()
                self.active_tasks.pop(chat_id, None)
                await self._send_message(chat_id, "🛑 *Emergency Stop Triggered!* All active operations have been forcefully terminated.", reply_markup=self._get_default_keyboard())
                return
            else:
                await self._send_message(chat_id, "⚠️ *No active operations running.*", reply_markup=self._get_default_keyboard())
                return

        # Standard request
        await self._send_message(chat_id, "⏳ *Processing command...*")
        
        session_id = f"telegram_{chat_id}"
        
        # Cancel any active running task first to avoid overlap
        existing_task = self.active_tasks.get(chat_id)
        if existing_task and not existing_task.done():
            existing_task.cancel()
            
        task = asyncio.create_task(self._process_and_reply(chat_id, text, session_id))
        self.active_tasks[chat_id] = task

    async def _process_and_reply(self, chat_id: str, text: str, session_id: str):
        full_response = ""
        try:
            async def _stream():
                nonlocal full_response
                async for chunk in orchestrator.process_user_input_stream(session_id, text):
                    if isinstance(chunk, dict):
                        continue
                    full_response += chunk

            # 120s hard timeout — prevents bot getting stuck forever on long agent tasks
            try:
                await asyncio.wait_for(_stream(), timeout=120.0)
            except asyncio.TimeoutError:
                logger.warning(f"Telegram stream timed out after 120s for: {text}")
                if full_response.strip():
                    await self._send_message(chat_id, full_response.strip(), reply_markup=self._get_default_keyboard())
                else:
                    await self._send_message(chat_id, "✅ কাজ হয়ে গেছে।", reply_markup=self._get_default_keyboard())
                return

            if full_response.strip():
                await self._send_message(chat_id, full_response.strip(), reply_markup=self._get_default_keyboard())
            else:
                await self._send_message(chat_id, "✅ কাজ হয়ে গেছে।", reply_markup=self._get_default_keyboard())

            # Auto send screenshot for visual/navigation commands
            trigger_screenshot = any(kw in text.lower() for kw in ["dekho", "look", "screen", "screenshot", "chrome", "google", "browser", "youtube", "gmail"])
            if trigger_screenshot:
                await self._send_screenshot(chat_id, "📷 *Current Screen State:*")
        except asyncio.CancelledError:
            logger.info(f"Task for chat_id {chat_id} was forcefully cancelled.")
            raise
        except Exception as e:
            logger.error(f"Error processing Telegram command: {e}")
            await self._send_message(chat_id, f"❌ *Error running command:* {e}", reply_markup=self._get_default_keyboard())
        finally:
            # Always clean up — prevent stale task references building up in memory
            self.active_tasks.pop(chat_id, None)
    def _get_default_keyboard(self) -> dict:
        return {
            "keyboard": [
                [{"text": "🛑 Emergency Stop"}, {"text": "📸 Get Screenshot"}],
                [{"text": "📊 Check Status"}, {"text": "🔑 WhatsApp Link"}],
                [{"text": "❓ Help & Guide"}, {"text": "👤 Unpair Bot"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }

    async def _send_message(self, chat_id: str, text: str, reply_markup: Optional[dict] = None):
        if not self.bot_token:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload, timeout=10.0)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def _send_screenshot(self, chat_id: str, caption: str):
        if not self.bot_token:
            return
        
        img, monitor = screen_capture.capture_as_pil()
        if not img:
            await self._send_message(chat_id, "⚠️ *Screenshot Blocked:* A sensitive application (e.g. Bank or Password Manager) is currently open on your screen to protect your privacy.", reply_markup=self._get_default_keyboard())
            return

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=75)
        photo_bytes = buffer.getvalue()

        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption, "reply_markup": json.dumps(self._get_default_keyboard()), "parse_mode": "Markdown"},
                    files={"photo": ("screenshot.jpg", photo_bytes, "image/jpeg")},
                    timeout=20.0
                )
        except Exception as e:
            logger.error(f"Failed to send Telegram screenshot: {e}")

    def _clean_duplicate_processes(self):
        try:
            import psutil
            current_pid = os.getpid()
            
            # Find all parent/ancestor PIDs of the current process to protect them
            protected_pids = {current_pid}
            try:
                curr = psutil.Process(current_pid)
                while curr.parent():
                    protected_pids.add(curr.parent().pid)
                    curr = curr.parent()
            except Exception:
                pass

            if os.name == 'nt':
                import json
                cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"Name = \'python.exe\'\\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"'
                output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
                if output.strip():
                    processes = json.loads(output)
                    if not isinstance(processes, list):
                        processes = [processes]
                    for p in processes:
                        if not p:
                            continue
                        pid = p.get("ProcessId")
                        cmdline = p.get("CommandLine") or ""
                        if pid and pid not in protected_pids:
                            # Only kill duplicate uvicorn backend workers/processes
                            if "uvicorn" in cmdline or "spawn_main" in cmdline:
                                logger.warning(f"Found conflicting Telegram process with PID {pid}, force killing it...")
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
            else:
                subprocess.run("fuser -k 8000/tcp", shell=True, capture_output=True)
        except Exception as e:
            logger.error(f"Failed to clean duplicate processes: {e}")

telegram_bot_manager = TelegramBotManager()
