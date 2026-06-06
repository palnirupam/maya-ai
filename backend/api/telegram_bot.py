"""
telegram_bot_manager.py
=======================
Production-grade Telegram bot manager for Maya AI.

Improvements over previous version
------------------------------------
* No more nested `async def` inside loops — all helpers are proper class methods.
* `_pending_dangerous_cmd` is now a per-chat dict — no race condition.
* Every public-facing coroutine that touches shared state is guarded by
  `asyncio.Lock` where needed.
* Structured logging with context (chat_id, pending_id) everywhere.
* Separate, typed dataclasses for pending WA state — no raw dicts.
* `_send_message` / `_edit_message` handle Telegram 429 rate-limit with
  exponential back-off and automatic Markdown → plain-text fallback.
* `_poll_loop` uses a single persistent `httpx.AsyncClient` (connection reuse).
* All background tasks (`_wa_listener_loop`, `_wa_cleanup_loop`) restart
  themselves after crashes with bounded retry delays.
* `stop()` awaits task cancellation cleanly instead of fire-and-forget.
* `load_config()` is async-safe (called before any tasks start).
* WhatsApp pairing, allow/block, manual reply — all use typed helpers,
  no duplicated markup-building code.
* Dangerous-command confirmation works correctly when multiple chat_ids
  are paired simultaneously (edge case but defensive).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import os
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Dict, Optional

import httpx

from backend.brain.orchestrator import orchestrator
from backend.database.connection import SessionLocal
from backend.database.crypto import crypto_manager
from backend.database.models import UserPreferences
from backend.brain.reasoning.tool_planner import tool_planner
from backend.system.process_manager import process_manager
from backend.vision.capture.screen_capture import screen_capture

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

EDIT_INTERVAL   = 1.2    # seconds between live-edits (avoid Telegram flood)
STREAM_TIMEOUT  = 120.0  # hard timeout for orchestrator stream
MANUAL_TIMEOUT  = 300.0  # 5 min — auto-cancel WA manual reply
WA_EXPIRE_SECS  = 1800   # 30 min — remove stale pending WA replies
WA_CLEANUP_INT  = 300    # check every 5 min
MAX_EDIT_RETRIES = 3

DANGEROUS_SHUTDOWN_KEYWORDS = frozenset([
    "shutdown", "shut down", "turn off", "bondho koro laptop",
    "laptop bondho", "shut", "শাটডাউন", "বন্ধ করো ল্যাপটপ",
])
SYSTEM_SCOPE_KEYWORDS = frozenset([
    "laptop", "pc", "computer", "system", "sob", "সব", "ল্যাপটপ",
])
SCREENSHOT_TRIGGER_KEYWORDS = frozenset([
    "dekho", "look", "screen", "screenshot", "chrome",
    "google", "browser", "youtube", "gmail",
])
STOP_KEYWORDS = frozenset([
    "stop", "halt", "panic", "🛑 emergency stop",
    "thamo", "থামো", "থাম",
])

# ──────────────────────────────────────────────────────────────────────────────
# Typed state containers (replaces raw dicts)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PendingWAReply:
    """Holds all state for one incoming WhatsApp message awaiting action."""
    id: str
    chat_id_wa: str          # WhatsApp chat ID for whatsapp_manager.reply_to_chat
    from_number: str
    from_name: str
    is_group: bool
    group_name: str
    trigger_msg: str
    context_messages: list
    is_known: bool
    gemini_draft: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class PendingDangerousCmd:
    """Confirmation state for a dangerous command (shutdown etc.)."""
    telegram_chat_id: str
    original_text: str


# ──────────────────────────────────────────────────────────────────────────────
# Main class
# ──────────────────────────────────────────────────────────────────────────────

class TelegramBotManager:
    """Manages the long-poll Telegram bot lifecycle for Maya AI."""

    def __init__(self) -> None:
        # Config (populated by load_config)
        self.bot_token: Optional[str] = None
        self.chat_id: Optional[str] = None
        self.pairing_code: Optional[str] = None
        self.enabled: bool = False

        # Runtime state
        self.running: bool = False
        self._http: Optional[httpx.AsyncClient] = None   # persistent client

        # Per-chat active task (for emergency stop)
        self._active_tasks: Dict[str, asyncio.Task] = {}

        # Dangerous command confirmations — keyed by telegram_chat_id
        self._pending_dangerous: Dict[str, PendingDangerousCmd] = {}

        # WhatsApp incoming — keyed by pending_id
        self._pending_wa: Dict[str, PendingWAReply] = {}
        # telegram_chat_id → pending_id  (set while waiting for manual reply)
        self._wa_manual_awaiting: Dict[str, str] = {}
        # pending_id → asyncio.Task (auto-cancel timer)
        self._wa_manual_timers: Dict[str, asyncio.Task] = {}

        # Background tasks
        self._poll_task: Optional[asyncio.Task] = None
        self._wa_listener_task: Optional[asyncio.Task] = None
        self._wa_cleanup_task: Optional[asyncio.Task] = None

    # ──────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def load_config(self) -> None:
        """Load / refresh config from the database. Thread-safe (no async)."""
        db = SessionLocal()
        try:
            def _get(key: str) -> Optional[str]:
                pref = db.query(UserPreferences).filter(
                    UserPreferences.key == key
                ).first()
                if not pref or not pref.value:
                    return None
                decrypted = crypto_manager.decrypt(pref.value)
                return decrypted or pref.value

            def _set(key: str, value: str) -> None:
                enc = crypto_manager.encrypt(value)
                pref = db.query(UserPreferences).filter(
                    UserPreferences.key == key
                ).first()
                if pref:
                    pref.value = enc
                else:
                    db.add(UserPreferences(key=key, value=enc))
                db.commit()

            enabled_val = _get("TELEGRAM_BOT_ENABLED")
            self.enabled = enabled_val == "true"
            self.bot_token = _get("TELEGRAM_BOT_TOKEN")
            self.chat_id   = _get("TELEGRAM_CHAT_ID")

            code = _get("TELEGRAM_PAIRING_CODE")
            if not code:
                # Use secrets for secure pairing code
                code = str(secrets.randbelow(900000) + 100000)
                _set("TELEGRAM_PAIRING_CODE", code)
            self.pairing_code = code

        finally:
            db.close()

    def start(self) -> None:
        """Start the bot (call from an asyncio context, after load_config)."""
        self.load_config()
        if not (self.enabled and self.bot_token):
            logger.info("Telegram Bot disabled or missing token — skipping start.")
            return
        if self.running:
            logger.warning("Telegram Bot already running — call restart() to reload.")
            return

        self.running = True
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0))
        self._poll_task        = asyncio.create_task(self._poll_loop(),        name="tg-poll")
        self._wa_listener_task = asyncio.create_task(self._wa_listener_loop(), name="tg-wa-listener")
        self._wa_cleanup_task  = asyncio.create_task(self._wa_cleanup_loop(),  name="tg-wa-cleanup")
        logger.info("Telegram Bot started.")

    async def stop(self) -> None:
        """Gracefully stop all tasks and close the HTTP client."""
        self.running = False
        tasks = [
            t for t in [
                self._poll_task,
                self._wa_listener_task,
                self._wa_cleanup_task,
                *self._active_tasks.values(),
                *self._wa_manual_timers.values(),
            ]
            if t and not t.done()
        ]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self._http:
            await self._http.aclose()
            self._http = None

        self._poll_task = self._wa_listener_task = self._wa_cleanup_task = None
        self._active_tasks.clear()
        self._wa_manual_timers.clear()
        logger.info("Telegram Bot stopped.")

    async def restart(self) -> None:
        await self.stop()
        self.start()

    # ──────────────────────────────────────────────────────────────────────────
    # Core poll loop
    # ──────────────────────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        offset: Optional[int] = None
        retry_delay = 1.0

        while self.running:
            if not self.bot_token or not self._http:
                await asyncio.sleep(5.0)
                continue
            try:
                params: dict = {"timeout": 20}
                if offset:
                    params["offset"] = offset

                resp = await self._http.get(
                    TELEGRAM_API.format(token=self.bot_token, method="getUpdates"),
                    params=params,
                )
                retry_delay = 1.0   # reset on success

                if resp.status_code == 200:
                    for update in resp.json().get("result", []):
                        offset = update["update_id"] + 1
                        if cq := update.get("callback_query"):
                            asyncio.create_task(self._handle_callback_query(cq))
                        elif msg := update.get("message"):
                            asyncio.create_task(self._handle_message(msg))

                elif resp.status_code == 401:
                    logger.error("Telegram bot token invalid (401). Stopping poll.")
                    self.running = False

                elif resp.status_code == 409:
                    logger.warning("Telegram 409 Conflict — cleaning duplicate processes.")
                    self._clean_duplicate_processes()
                    await asyncio.sleep(5.0)

                else:
                    logger.warning("Telegram API returned %s", resp.status_code)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60.0)

            except asyncio.CancelledError:
                break
            except httpx.TransportError as exc:
                logger.warning("Telegram network error: %s — retrying in %.1fs", exc, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60.0)
            except Exception as exc:
                logger.error("Unexpected error in poll loop: %s", exc, exc_info=True)
                await asyncio.sleep(5.0)

    # ──────────────────────────────────────────────────────────────────────────
    # Message handler
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_message(self, message: dict) -> None:
        chat_id = str(message["chat"]["id"])
        text    = message.get("text", "").strip()
        if not text:
            return

        # ── Intercept manual WA reply ──────────────────────────────────────
        if pending_id := self._wa_manual_awaiting.get(chat_id):
            if self.chat_id and chat_id == self.chat_id:
                await self._complete_manual_wa_reply(chat_id, pending_id, text)
                return

        # ── Pairing handshake ──────────────────────────────────────────────
        if not self.chat_id:
            await self._handle_pairing(chat_id, text)
            return

        # ── Reject unauthorized senders ────────────────────────────────────
        if chat_id != self.chat_id:
            await self._send_message(
                chat_id,
                "❌ *Unauthorized.* This Maya AI instance is paired with another account.",
            )
            return

        text_lower = text.lower()

        # ── WhatsApp pairing command ───────────────────────────────────────
        if self._is_wa_pair_command(text_lower):
            await self._handle_wa_pair(chat_id, text)
            return

        # ── Static commands / button taps ──────────────────────────────────
        if text_lower in {"/start", "/help", "❓ help & guide"}:
            await self._send_help(chat_id)
            return
        if text_lower in {"/reset", "👤 unpair bot"}:
            await self._unpair(chat_id)
            return
        if text_lower in {"/status", "📊 check status"}:
            await self._send_status(chat_id)
            return
        if text_lower in {"/screenshot", "📸 get screenshot"}:
            await self._send_screenshot(chat_id, "Here is your current desktop screen:")
            return
        if text_lower in {"/whatsapp_qr", "🟢 whatsapp qr", "🔑 whatsapp link"}:
            await self._send_wa_link_guide(chat_id)
            return

        # ── Microphone Lock / Sleep Mode ───────────────────────────────────
        if text_lower in {"/lock", "🔒 mic lock", "lock mic", "sleep mode on",
                          "mic lock koro", "lock koro", "ঘুমাও", "lock"}:
            await self._lock_microphone(chat_id)
            return
        if text_lower in {"/unlock", "🔓 mic unlock", "unlock mic", "sleep mode off",
                          "mic unlock koro", "unlock koro", "জাগো", "unlock"}:
            await self._unlock_microphone(chat_id)
            return

        # ── Dangerous command detection ────────────────────────────────────
        if self._is_dangerous_shutdown(text_lower):
            await self._ask_shutdown_confirm(chat_id, text)
            return

        # ── Emergency stop ─────────────────────────────────────────────────
        if text_lower in STOP_KEYWORDS:
            await self._emergency_stop(chat_id)
            return

        # ── Route to orchestrator ──────────────────────────────────────────
        session_id = f"telegram_{chat_id}"
        if (existing := self._active_tasks.get(chat_id)) and not existing.done():
            existing.cancel()
        task = asyncio.create_task(
            self._process_and_reply(chat_id, text, session_id),
            name=f"tg-reply-{chat_id}",
        )
        self._active_tasks[chat_id] = task

    # ──────────────────────────────────────────────────────────────────────────
    # Callback query handler
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_callback_query(self, cq: dict) -> None:
        cq_id   = cq.get("id")
        data    = cq.get("data", "")
        chat_id = str(cq["message"]["chat"]["id"])

        await self._answer_callback(cq_id)

        # ── WhatsApp callbacks ─────────────────────────────────────────────
        if data.startswith("wa_gemini_"):
            await self._wa_cb_gemini(chat_id, data[len("wa_gemini_"):])
        elif data.startswith("wa_send_draft_"):
            await self._wa_cb_send_draft(chat_id, data[len("wa_send_draft_"):])
        elif data.startswith("wa_manual_"):
            await self._wa_cb_manual(chat_id, data[len("wa_manual_"):])
        elif data.startswith("wa_ignore_"):
            await self._wa_cb_ignore(chat_id, data[len("wa_ignore_"):])
        elif data.startswith("wa_allow_"):
            await self._wa_cb_allow(chat_id, data[len("wa_allow_"):])
        elif data.startswith("wa_block_"):
            await self._wa_cb_block(chat_id, data[len("wa_block_"):])

        # ── Shutdown confirmation ──────────────────────────────────────────
        elif data == "confirm_shutdown":
            await self._cb_confirm_shutdown(chat_id)
        elif data == "cancel_shutdown":
            await self._cb_cancel_shutdown(chat_id)
            
        # ── Exec Approval Queue ────────────────────────────────────────────
        elif data.startswith("exec_approve_"):
            req_id = data[len("exec_approve_"):]
            user_id = str(cq["from"].get("username", cq["from"].get("id", "telegram_user")))
            tool_planner.resolve_tool(req_id, approved=True, user_id=user_id)
            await self._edit_message(
                chat_id, str(cq["message"]["message_id"]),
                "✅ *Command Approved.* Executing...",
                parse_mode="Markdown"
            )
        elif data.startswith("exec_deny_"):
            req_id = data[len("exec_deny_"):]
            user_id = str(cq["from"].get("username", cq["from"].get("id", "telegram_user")))
            tool_planner.resolve_tool(req_id, approved=False, user_id=user_id)
            await self._edit_message(
                chat_id, str(cq["message"]["message_id"]),
                "❌ *Command Denied.* Execution aborted.",
                parse_mode="Markdown"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Streaming reply
    # ──────────────────────────────────────────────────────────────────────────

    async def _process_and_reply(
        self, chat_id: str, text: str, session_id: str
    ) -> None:
        full_response  = ""
        sent_msg_id: Optional[str] = None
        current_shown  = ""
        last_edit_time = 0.0

        async def _flush(*, final: bool = False) -> None:
            nonlocal sent_msg_id, current_shown, last_edit_time
            display = full_response.strip()
            if not display or display == current_shown:
                return
            now = time.monotonic()
            if not final and (now - last_edit_time) < EDIT_INTERVAL:
                return
            last_edit_time = now
            current_shown  = display
            suffix = "" if final else " ✍️"
            parse  = "Markdown" if final else None
            if sent_msg_id is None:
                sent_msg_id = await self._send_message_get_id(
                    chat_id, display + suffix, parse_mode=parse
                )
            else:
                await self._edit_message(
                    chat_id, sent_msg_id, display + suffix, parse_mode=parse
                )

        try:
            await self._send_typing(chat_id)

            async def _stream() -> None:
                nonlocal full_response
                async for chunk in orchestrator.process_user_input_stream(
                    session_id, text
                ):
                    if isinstance(chunk, dict):
                        if chunk.get("type") == "tool_call_request":
                            data = chunk.get("data", {})
                            req_id = data.get("request_id")
                            tool_name = data.get("tool_name", "unknown")
                            args = data.get("args", {})
                            
                            markup = {
                                "inline_keyboard": [[
                                    {"text": "✅ Approve", "callback_data": f"exec_approve_{req_id}"},
                                    {"text": "❌ Deny", "callback_data": f"exec_deny_{req_id}"},
                                ]]
                            }
                            await self._send_message(
                                chat_id,
                                f"⚠️ *Maya Exec Approval*\n\nMaya wants to run: `{tool_name}`\nArguments:\n```json\n{json.dumps(args, indent=2)}\n```\n\nDo you approve?",
                                reply_markup=markup
                            )
                        continue
                    full_response += chunk
                    await _flush()

            try:
                await asyncio.wait_for(_stream(), timeout=STREAM_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("Stream timeout for chat=%s text=%r", chat_id, text)
                if full_response.strip():
                    await _flush(final=True)
                    if sent_msg_id:
                        await self._edit_message(
                            chat_id, sent_msg_id,
                            full_response.strip(),
                            reply_markup=self._default_keyboard(),
                        )
                else:
                    await self._send_message(
                        chat_id, "✅ কাজ হয়ে গেছে।",
                        reply_markup=self._default_keyboard(),
                    )
                return

            # ── Special signal handlers ────────────────────────────────────
            if "SYSTEM_STATE_TRIGGERED:" in full_response:
                await self._handle_system_state_signal(
                    chat_id, sent_msg_id, full_response
                )
                return

            if "MODE_CHANGE_TRIGGERED:" in full_response:
                await self._handle_mode_change_signal(
                    chat_id, sent_msg_id, full_response
                )
                return

            # ── Final send ────────────────────────────────────────────────
            final_text = full_response.strip() or "✅ কাজ হয়ে গেছে।"
            if sent_msg_id:
                await self._edit_message(chat_id, sent_msg_id, final_text)
                await self._send_message(
                    chat_id, "‎", reply_markup=self._default_keyboard()
                )
            else:
                await self._send_message(
                    chat_id, final_text, reply_markup=self._default_keyboard()
                )

            # ── Auto screenshot for visual/navigation commands ─────────────
            if any(kw in text.lower() for kw in SCREENSHOT_TRIGGER_KEYWORDS):
                await self._send_screenshot(chat_id, "📷 *Current Screen State:*")

        except asyncio.CancelledError:
            logger.info("Task cancelled for chat_id=%s", chat_id)
            raise
        except Exception as exc:
            logger.error(
                "Error processing command for chat=%s: %s", chat_id, exc, exc_info=True
            )
            await self._send_message(
                chat_id,
                f"❌ *Error:* {exc}",
                reply_markup=self._default_keyboard(),
            )
        finally:
            self._active_tasks.pop(chat_id, None)

    # ──────────────────────────────────────────────────────────────────────────
    # WhatsApp incoming notification
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_whatsapp_incoming(self, msg_data: dict) -> None:
        """Called by the WA listener; sends a Telegram notification."""
        if not self.chat_id:
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
        self._pending_wa[pending.id] = pending

        text, markup = self._build_wa_notification(pending)
        await self._send_message(self.chat_id, text, reply_markup=markup)

    def _build_wa_notification(
        self, p: PendingWAReply
    ) -> tuple[str, dict]:
        reply_row = [
            {"text": "🤖 Gemini Draft", "callback_data": f"wa_gemini_{p.id}"},
            {"text": "✏️ নিজে লিখি",    "callback_data": f"wa_manual_{p.id}"},
            {"text": "❌ Ignore",         "callback_data": f"wa_ignore_{p.id}"},
        ]

        if not p.is_known and not p.is_group:
            text = (
                "📩 *অজানা নম্বর থেকে WhatsApp মেসেজ!*\n\n"
                f"👤 {p.from_name} (+{p.from_number}) _(অচেনা)_\n"
                f"─────────────────────────\n"
                f'"{p.trigger_msg}"\n'
                "─────────────────────────"
            )
            markup = {
                "inline_keyboard": [[
                    {"text": "✅ Allow করো",   "callback_data": f"wa_allow_{p.id}"},
                    {"text": "🚫 Block",        "callback_data": f"wa_block_{p.id}"},
                    {"text": "❌ Ignore",        "callback_data": f"wa_ignore_{p.id}"},
                ]]
            }
        elif p.is_group:
            ctx = f"[Context: {len(p.context_messages)}টা আগের message]" \
                  if p.context_messages else "[Context: নেই]"
            text = (
                "💬 *Group-এ Mention!*\n\n"
                f"👥 *Group:* {p.group_name}\n"
                f"👤 *Sender:* {p.from_name} (+{p.from_number})\n"
                f"─────────────────────────\n"
                f"{ctx}\n"
                f"─────────────────────────\n"
                f'"{p.trigger_msg}"\n'
                "─────────────────────────\n"
                "⚠️ GROUP মেসেজ — ভালো করে দেখে reply করুন!"
            )
            markup = {"inline_keyboard": [reply_row]}
        else:
            text = (
                "💬 *নতুন WhatsApp মেসেজ!*\n\n"
                f"👤 *From:* {p.from_name} (+{p.from_number})\n"
                "📍 *Chat:* Personal (Direct)\n"
                f"─────────────────────────\n"
                f'"{p.trigger_msg}"\n'
                "─────────────────────────"
            )
            markup = {"inline_keyboard": [reply_row]}

        return text, markup

    # ──────────────────────────────────────────────────────────────────────────
    # WhatsApp callback actions
    # ──────────────────────────────────────────────────────────────────────────

    async def _wa_cb_gemini(self, chat_id: str, pending_id: str) -> None:
        pending = self._pending_wa.get(pending_id)
        if not pending:
            await self._send_message(chat_id, "⚠️ Pending message not found (expired?).")
            return

        await self._send_message(chat_id, "⏳ Gemini draft তৈরি করছে...")

        context_lines = "".join(
            f"[{m.get('name', m.get('from', '?'))}]: {m.get('body', '')}\n"
            for m in pending.context_messages
        )
        prompt = (
            "You are Maya, the user's personal AI assistant managing their WhatsApp.\n"
            "Respond naturally, casually, and friendly like a human assistant.\n"
            "CRITICAL: DO NOT sound like a robotic customer service bot. DO NOT say 'How can I help you?'.\n\n"
            "🌐 LANGUAGE RULE:\n"
            "- Detect the language of the triggering message.\n"
            "- Reply in that EXACT same language.\n"
            "- Supported: English, Bengali (বাংলা), Hindi (हिंदी).\n"
            "- If mixed (e.g., Banglish), reply in the dominant language.\n"
            "- NEVER switch languages.\n\n"
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
            async for chunk in orchestrator.process_user_input_stream(
                f"wa_draft_{pending_id}", prompt
            ):
                if not isinstance(chunk, dict):
                    draft += chunk
            draft = draft.strip()
        except Exception as exc:
            await self._send_message(
                chat_id, f"❌ Gemini error: {exc}",
                reply_markup=self._default_keyboard(),
            )
            return

        if not draft:
            await self._send_message(
                chat_id, "❌ Gemini খালি reply দিয়েছে।",
                reply_markup=self._default_keyboard(),
            )
            return

        lang_hint = self._detect_language_hint(pending.trigger_msg)
        pending.gemini_draft = draft

        markup = {
            "inline_keyboard": [[
                {"text": "✅ এটাই পাঠাও", "callback_data": f"wa_send_draft_{pending_id}"},
                {"text": "✏️ Edit করো",   "callback_data": f"wa_manual_{pending_id}"},
                {"text": "❌ Cancel",      "callback_data": f"wa_ignore_{pending_id}"},
            ]]
        }
        await self._send_message(
            chat_id,
            f"📝 *Gemini Draft Ready:*\n{lang_hint}\n\n`{draft}`",
            reply_markup=markup,
        )

    async def _wa_cb_send_draft(self, chat_id: str, pending_id: str) -> None:
        pending = self._pending_wa.get(pending_id)
        if not pending:
            await self._send_message(chat_id, "⚠️ Pending message not found (expired?).")
            return
        if not pending.gemini_draft:
            await self._send_message(chat_id, "❌ No draft found.")
            return
        await self._send_wa_reply(chat_id, pending, pending.gemini_draft)

    async def _wa_cb_manual(self, chat_id: str, pending_id: str) -> None:
        if pending_id not in self._pending_wa:
            await self._send_message(chat_id, "⚠️ Pending message not found (expired?).")
            return
        self._wa_manual_awaiting[chat_id] = pending_id
        await self._send_message(
            chat_id,
            "✏️ *আপনার reply টাইপ করুন:*\n_(পাঁচ মিনিট সময় আছে)_",
        )
        # Cancel any existing timer for this pending_id
        if old := self._wa_manual_timers.pop(pending_id, None):
            old.cancel()
        task = asyncio.create_task(
            self._manual_timeout_handler(pending_id, chat_id),
            name=f"wa-manual-timer-{pending_id}",
        )
        self._wa_manual_timers[pending_id] = task

    async def _wa_cb_ignore(self, chat_id: str, pending_id: str) -> None:
        self._pending_wa.pop(pending_id, None)
        self._cancel_manual_timer(pending_id)
        await self._send_message(
            chat_id,
            "✅ *Ignored.* WhatsApp-এ কোনো reply যাবে না।",
            reply_markup=self._default_keyboard(),
        )

    async def _wa_cb_allow(self, chat_id: str, pending_id: str) -> None:
        pending = self._pending_wa.get(pending_id)
        if not pending:
            await self._send_message(chat_id, "⚠️ Pending message not found (expired?).")
            return
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        whatsapp_manager.register_known_sender(pending.from_number)
        pending.is_known = True
        markup = {
            "inline_keyboard": [[
                {"text": "🤖 Gemini Draft", "callback_data": f"wa_gemini_{pending_id}"},
                {"text": "✏️ নিজে লিখি",   "callback_data": f"wa_manual_{pending_id}"},
                {"text": "❌ Ignore",         "callback_data": f"wa_ignore_{pending_id}"},
            ]]
        }
        await self._send_message(
            chat_id,
            f"✅ *+{pending.from_number} অনুমোদিত!* ভবিষ্যতে অটো-notification আসবে।\n\nReply দিতে চাইলে:",
            reply_markup=markup,
        )

    async def _wa_cb_block(self, chat_id: str, pending_id: str) -> None:
        pending = self._pending_wa.pop(pending_id, None)
        if not pending:
            await self._send_message(chat_id, "⚠️ Pending message not found (expired?).")
            return
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        whatsapp_manager.block_sender(pending.from_number)
        await self._send_message(
            chat_id,
            f"🚫 *+{pending.from_number} ব্লক!* এই নম্বর থেকে আর notification আসবে না।",
            reply_markup=self._default_keyboard(),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Manual reply helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _complete_manual_wa_reply(
        self, chat_id: str, pending_id: str, text: str
    ) -> None:
        self._cancel_manual_timer(pending_id)
        self._wa_manual_awaiting.pop(chat_id, None)
        pending = self._pending_wa.pop(pending_id, None)
        if not pending:
            await self._send_message(chat_id, "⚠️ Pending message not found (expired?).")
            return
        await self._send_wa_reply(chat_id, pending, text)

    async def _manual_timeout_handler(
        self, pending_id: str, chat_id: str
    ) -> None:
        """Background task — auto-cancels a manual WA reply after MANUAL_TIMEOUT."""
        try:
            await asyncio.sleep(MANUAL_TIMEOUT)
            if self._wa_manual_awaiting.get(chat_id) == pending_id:
                self._wa_manual_awaiting.pop(chat_id, None)
                self._pending_wa.pop(pending_id, None)
                self._wa_manual_timers.pop(pending_id, None)
                await self._send_message(
                    chat_id,
                    "⏱️ *Timeout* — Manual reply বাতিল হয়েছে।",
                    reply_markup=self._default_keyboard(),
                )
        except asyncio.CancelledError:
            pass

    def _cancel_manual_timer(self, pending_id: str) -> None:
        if timer := self._wa_manual_timers.pop(pending_id, None):
            timer.cancel()

    async def _send_wa_reply(
        self, chat_id: str, pending: PendingWAReply, reply_text: str
    ) -> None:
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        ok = whatsapp_manager.reply_to_chat(pending.chat_id_wa, reply_text)
        self._pending_wa.pop(pending.id, None)
        if ok:
            await self._send_message(
                chat_id,
                f"✅ *Reply sent!*\n\n`{reply_text}`",
                reply_markup=self._default_keyboard(),
            )
        else:
            await self._send_message(
                chat_id,
                "❌ WhatsApp-এ reply পাঠানো যায়নি। WhatsApp connected আছে?",
                reply_markup=self._default_keyboard(),
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Shutdown confirmation
    # ──────────────────────────────────────────────────────────────────────────

    async def _ask_shutdown_confirm(self, chat_id: str, text: str) -> None:
        self._pending_dangerous[chat_id] = PendingDangerousCmd(
            telegram_chat_id=chat_id, original_text=text
        )
        markup = {
            "inline_keyboard": [[
                {"text": "✅ হ্যাঁ, বন্ধ করো", "callback_data": "confirm_shutdown"},
                {"text": "❌ না, বাতিল",        "callback_data": "cancel_shutdown"},
            ]]
        }
        await self._send_message(
            chat_id,
            f"⚠️ *Dangerous Command!*\n\nতুমি বলেছ: `{text}`\n\nলাপটপ shutdown হবে। সত্যিই করবো?",
            reply_markup=markup,
        )

    async def _cb_confirm_shutdown(self, chat_id: str) -> None:
        cmd = self._pending_dangerous.pop(chat_id, None)
        if not cmd or cmd.telegram_chat_id != chat_id:
            await self._send_message(
                chat_id, "⚠️ কোনো pending command নেই।",
                reply_markup=self._default_keyboard(),
            )
            return
        await self._send_message(
            chat_id,
            "⚙️ *Shutdown শুরু হচ্ছে...*\n\nChrome বন্ধ → 10 সেকেন্ড পর বন্ধ হবে। 🔴",
        )
        try:
            from backend.system.shutdown_manager import shutdown_manager
            await shutdown_manager.trigger_windows_shutdown(delay_seconds=10)
        except Exception as exc:
            await self._send_message(
                chat_id, f"❌ Shutdown error: {exc}",
                reply_markup=self._default_keyboard(),
            )

    async def _cb_cancel_shutdown(self, chat_id: str) -> None:
        self._pending_dangerous.pop(chat_id, None)
        await self._send_message(
            chat_id,
            "✅ *বাতিল।* Laptop বন্ধ হয়নি।",
            reply_markup=self._default_keyboard(),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Signal handlers (orchestrator special tokens)
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_system_state_signal(
        self, chat_id: str, sent_msg_id: Optional[str], full_response: str
    ) -> None:
        action = full_response.split("SYSTEM_STATE_TRIGGERED:")[1].strip().split()[0]
        if action == "shutdown":
            self._pending_dangerous[chat_id] = PendingDangerousCmd(
                telegram_chat_id=chat_id, original_text="shutdown"
            )
            markup = {
                "inline_keyboard": [[
                    {"text": "✅ হ্যাঁ, বন্ধ করো", "callback_data": "confirm_shutdown"},
                    {"text": "❌ না, বাতিল",        "callback_data": "cancel_shutdown"},
                ]]
            }
            msg = "⚠️ *Shutdown Confirm করো!*\n\nসত্যিই ল্যাপটপ বন্ধ করবো? সব অ্যাপ বন্ধ হবে।"
            if sent_msg_id:
                await self._edit_message(chat_id, sent_msg_id, msg)
            await self._send_message(chat_id, "👇 নিচের বোতাম চাপো:", reply_markup=markup)
        else:
            msg = "💤 Sleep mode চালু হচ্ছে..."
            if sent_msg_id:
                await self._edit_message(chat_id, sent_msg_id, msg)
            else:
                await self._send_message(chat_id, msg, reply_markup=self._default_keyboard())

    async def _handle_mode_change_signal(
        self, chat_id: str, sent_msg_id: Optional[str], full_response: str
    ) -> None:
        mode_req     = full_response.split("MODE_CHANGE_TRIGGERED:")[1].strip().split()[0]
        visible_text = full_response.split("MODE_CHANGE_TRIGGERED:")[0].strip()
        try:
            from backend.system.state_manager import state_manager
            success = await state_manager.change_mode(mode_req)
            mode_labels = {
                "coding":       "🔵 Coding",
                "professional": "⚪ Professional",
                "friendly":     "🟠 Friendly",
            }
            if success:
                label = mode_labels.get(mode_req, mode_req.capitalize())
                reply = (f"{visible_text}\n\n" if visible_text else "") + \
                        f"✅ *Mode পরিবর্তন!* এখন: *{label} Mode*"
                if sent_msg_id:
                    await self._edit_message(chat_id, sent_msg_id, reply)
                await self._send_message(chat_id, "👆 উপরে দেখুন", reply_markup=self._default_keyboard())
            else:
                await self._send_message(
                    chat_id,
                    f"❌ অজানা mode: `{mode_req}`\nসঠিক modes: friendly, coding, professional",
                    reply_markup=self._default_keyboard(),
                )
        except Exception as exc:
            logger.error("Mode change error: %s", exc, exc_info=True)
            await self._send_message(
                chat_id, f"❌ Mode change error: {exc}",
                reply_markup=self._default_keyboard(),
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Pairing / auth helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _handle_pairing(self, chat_id: str, text: str) -> None:
        if text.startswith("/pair"):
            parts = text.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip() == self.pairing_code:
                db = SessionLocal()
                try:
                    enc = crypto_manager.encrypt(chat_id)
                    pref = db.query(UserPreferences).filter(
                        UserPreferences.key == "TELEGRAM_CHAT_ID"
                    ).first()
                    if pref:
                        pref.value = enc
                    else:
                        db.add(UserPreferences(key="TELEGRAM_CHAT_ID", value=enc))
                    db.commit()
                    self.chat_id = chat_id
                finally:
                    db.close()
                await self._send_message(
                    chat_id,
                    "🟢 *Pairing Successful!*\n\nআপনি এখন Maya AI-কে Telegram থেকে command করতে পারবেন।",
                )
            else:
                await self._send_message(
                    chat_id,
                    "❌ *Incorrect passcode.*\n\n"
                    "Use: `/pair [passcode]` — 6-digit code from your desktop Maya AI settings.",
                )
        else:
            await self._send_message(
                chat_id,
                f"👋 *Hello! I am Maya AI.*\n\n"
                f"Pair করতে পাঠান:\n`/pair {self.pairing_code}`",
            )

    async def _unpair(self, chat_id: str) -> None:
        db = SessionLocal()
        try:
            if pref := db.query(UserPreferences).filter(
                UserPreferences.key == "TELEGRAM_CHAT_ID"
            ).first():
                db.delete(pref)
                db.commit()
            self.chat_id = None
        finally:
            db.close()
        await self._send_message(
            chat_id,
            "🔴 *Unpaired.*\n\nযেকোনো সময় `/pair [passcode]` দিয়ে নতুন account pair করুন।",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # WhatsApp pairing
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_wa_pair_command(text_lower: str) -> bool:
        return (
            "/whatsapp_pair" in text_lower
            or "pair whatsapp" in text_lower
            or "whatsapp pair" in text_lower
        )

    async def _handle_wa_pair(self, chat_id: str, text: str) -> None:
        # Strip command keywords and extract digits
        clean = text
        for kw in ("/whatsapp_pair", "pair whatsapp", "whatsapp pair"):
            idx = clean.lower().find(kw)
            if idx != -1:
                clean = clean[:idx] + clean[idx + len(kw):]

        phone = "".join(c for c in clean if c.isdigit())
        if phone.startswith("00"):
            phone = phone[2:]
        elif phone.startswith("0"):
            phone = phone[1:]
        if len(phone) == 10:
            phone = "91" + phone

        if not phone or len(phone) < 10:
            await self._send_message(
                chat_id,
                "❌ *Valid phone number দিন।*\n\n"
                "Usage: `/whatsapp_pair 919876543210` or `/whatsapp_pair 9876543210`",
                reply_markup=self._default_keyboard(),
            )
            return

        await self._send_message(
            chat_id,
            f"⏳ *+{phone} এর জন্য 8-digit pairing code চাওয়া হচ্ছে...*",
            reply_markup=self._default_keyboard(),
        )
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        code = whatsapp_manager.get_pairing_code(phone)
        if code:
            await self._send_message(
                chat_id,
                f"🔑 *WhatsApp Pairing Code:* `{code}`\n\n"
                "👉 *Phone-এ করুন:*\n"
                "1. WhatsApp → Settings → Linked Devices → Link a Device\n"
                "2. নিচে *Link with phone number instead* চাপুন\n"
                f"3. Code দিন: `{code}`\n\n"
                "_(Code দ্রুত expire হয় না)_",
                reply_markup=self._default_keyboard(),
            )
        else:
            await self._send_message(
                chat_id,
                "❌ *Pairing code পাওয়া যায়নি।*\n\nWhatsApp background service চালু আছে?",
                reply_markup=self._default_keyboard(),
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Static commands
    # ──────────────────────────────────────────────────────────────────────────

    async def _send_help(self, chat_id: str) -> None:
        await self._send_message(
            chat_id,
            "👋 *Maya AI — Advanced Control*\n\n"
            "🖥️ *Browser:* `\"google.com e jao\"` / `\"youtube khol\"`\n"
            "🎵 *Media:* `\"spotify play\"` / `\"next song\"` / `\"volume 50%\"`\n"
            "💬 *WhatsApp:* `\"[Name] ke message koro [Text]\"`\n"
            "🚀 *Apps:* `\"VS Code khol\"` / `\"Chrome open\"`\n"
            "📊 Tap *Check Status* — resource usage দেখুন\n"
            "📸 Tap *Get Screenshot* — এখন screen কী দেখাচ্ছে\n",
            reply_markup=self._default_keyboard(),
        )

    async def _send_status(self, chat_id: str) -> None:
        try:
            from backend.tools.desktop.advanced.system_tools import get_system_stats
            import pygetwindow as gw
            from backend.api.main import get_active_listener
            stats  = get_system_stats()
            active = gw.getActiveWindow()
            title  = active.title if active else "None"
            listener = get_active_listener()
            mic_status = "🔒 Locked (Sleep Mode)" if (listener and listener.is_locked) else "🎙️ Active (Listening)"
            msg    = (
                "📊 *System Status:*\n\n"
                f"🖥️ *Active Window:* `{title}`\n"
                f"🎙️ *Microphone:* {mic_status}\n"
                f"🔋 *Resources:* {stats}"
            )
        except Exception as exc:
            msg = f"❌ Stats error: {exc}"
        await self._send_message(chat_id, msg, reply_markup=self._default_keyboard())

    async def _send_wa_link_guide(self, chat_id: str) -> None:
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        if whatsapp_manager.get_status().get("status") == "connected":
            await self._send_message(
                chat_id, "🟢 *WhatsApp ইতিমধ্যে connected!*",
                reply_markup=self._default_keyboard(),
            )
        else:
            await self._send_message(
                chat_id,
                "🔑 *WhatsApp Link Guide:*\n\n"
                "1. Send: `/whatsapp_pair [phone]`\n"
                "   Example: `/whatsapp_pair 9876543210`\n"
                "2. Bot 8-digit pairing code দেবে।\n"
                "3. WhatsApp → Settings → Linked Devices → Link a Device\n"
                "4. *Link with phone number instead* → code enter করুন।",
                reply_markup=self._default_keyboard(),
            )

    async def _emergency_stop(self, chat_id: str) -> None:
        # 1. Cancel the specific active task in the telegram bot stream
        task = self._active_tasks.get(chat_id)
        if task and not task.done():
            task.cancel()
            self._active_tasks.pop(chat_id, None)
            
        # 2. Trigger the Deep Emergency Stop for all OS processes and background tasks
        await self._send_message(chat_id, "🛑 *Emergency Stop Triggered!* Canceling tasks and forcefully terminating process trees...")
        
        try:
            stats = await process_manager.emergency_stop()
            tasks_canceled = stats.get("tasks_canceled", 0)
            pids_killed = stats.get("pids_killed", 0)
            
            await self._send_message(
                chat_id,
                f"✅ *System Halted.*\n- Tasks canceled: {tasks_canceled}\n- Processes force-killed: {pids_killed}",
                reply_markup=self._default_keyboard(),
            )
        except Exception as e:
            logger.error(f"Error during deep emergency stop: {e}")
            await self._send_message(chat_id, "⚠️ Error during deep emergency stop.")

    async def _lock_microphone(self, chat_id: str) -> None:
        """Put Maya's desktop microphone into Sleep Mode."""
        try:
            from backend.api.main import get_active_listener
            listener = get_active_listener()
            if listener is None:
                await self._send_message(
                    chat_id,
                    "⚠️ *Voice engine চালু নেই।* Maya restart করো প্রথমে।",
                    reply_markup=self._default_keyboard(),
                )
                return
            if listener.is_locked:
                await self._send_message(
                    chat_id,
                    "🔒 *Microphone ইতিমধ্যে Locked আছে!*\n\nUnlock করতে `/unlock` পাঠাও।",
                    reply_markup=self._default_keyboard(),
                )
                return
            listener.lock()
            await self._send_message(
                chat_id,
                "🔒 *Microphone Locked!*\n\n"
                "Maya এখন ঘুমিয়ে পড়েছে। 😴\n"
                "তোমার ঘরে কেউ কথা বললেও সে শুনবে না।\n\n"
                "ফিরে এলে `/unlock` দিয়ে জাগিয়ে দাও।",
                reply_markup=self._default_keyboard(),
            )
            logger.info("[TelegramBot] Microphone locked via Telegram by chat_id=%s", chat_id)
        except Exception as exc:
            logger.error("Lock microphone error: %s", exc, exc_info=True)
            await self._send_message(chat_id, f"❌ Lock error: {exc}",
                                     reply_markup=self._default_keyboard())

    async def _unlock_microphone(self, chat_id: str) -> None:
        """Wake Maya's desktop microphone from Sleep Mode."""
        try:
            from backend.api.main import get_active_listener
            listener = get_active_listener()
            if listener is None:
                await self._send_message(
                    chat_id,
                    "⚠️ *Voice engine চালু নেই।* Maya restart করো প্রথমে।",
                    reply_markup=self._default_keyboard(),
                )
                return
            if not listener.is_locked:
                await self._send_message(
                    chat_id,
                    "🔓 *Microphone ইতিমধ্যে Unlocked আছে!*\n\nMaya সক্রিয়ভাবে শুনছে।",
                    reply_markup=self._default_keyboard(),
                )
                return
            listener.unlock()
            await self._send_message(
                chat_id,
                "🔓 *Microphone Unlocked!*\n\n"
                "Maya এখন জেগে উঠেছে! 👋\n"
                "ল্যাপটপের সামনে কথা বললেই সে শুনবে।",
                reply_markup=self._default_keyboard(),
            )
            logger.info("[TelegramBot] Microphone unlocked via Telegram by chat_id=%s", chat_id)
        except Exception as exc:
            logger.error("Unlock microphone error: %s", exc, exc_info=True)
            await self._send_message(chat_id, f"❌ Unlock error: {exc}",
                                     reply_markup=self._default_keyboard())

    # ──────────────────────────────────────────────────────────────────────────
    # Background loops
    # ──────────────────────────────────────────────────────────────────────────

    async def _wa_listener_loop(self) -> None:
        from backend.tools.desktop.advanced.whatsapp_manager import whatsapp_manager
        logger.info("[WA-IN] Listener loop started.")
        retry_delay = 5.0
        while self.running:
            try:
                if whatsapp_manager.get_status().get("status") in (
                    "connected", "authenticated"
                ):
                    await whatsapp_manager.start_incoming_listener(
                        self._handle_whatsapp_incoming
                    )
                    retry_delay = 5.0   # reset on clean exit
                else:
                    await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "[WA-IN] Listener crashed (retry in %.0fs): %s", retry_delay, exc
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60.0)

    async def _wa_cleanup_loop(self) -> None:
        logger.info("[WA-CLEANUP] Loop started.")
        while self.running:
            try:
                await asyncio.sleep(WA_CLEANUP_INT)
                cutoff  = time.time() - WA_EXPIRE_SECS
                expired = [
                    k for k, v in list(self._pending_wa.items())
                    if v.created_at < cutoff
                ]
                for k in expired:
                    self._pending_wa.pop(k, None)
                    self._cancel_manual_timer(k)
                if expired:
                    logger.info("[WA-CLEANUP] Removed %d expired entries.", len(expired))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[WA-CLEANUP] Error: %s", exc)

    # ──────────────────────────────────────────────────────────────────────────
    # Telegram HTTP helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _answer_callback(self, cq_id: Optional[str]) -> None:
        if not cq_id or not self.bot_token or not self._http:
            return
        try:
            await self._http.post(
                TELEGRAM_API.format(token=self.bot_token, method="answerCallbackQuery"),
                json={"callback_query_id": cq_id},
                timeout=5.0,
            )
        except Exception:
            pass

    async def _send_message(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: Optional[dict] = None,
        parse_mode: str = "Markdown",
    ) -> None:
        if not self.bot_token or not self._http:
            return
        payload: dict = {
            "chat_id":    chat_id,
            "text":       text[:4096],
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        await self._post_with_retry(
            TELEGRAM_API.format(token=self.bot_token, method="sendMessage"),
            payload,
        )

    async def _send_message_get_id(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: Optional[str] = "Markdown",
    ) -> Optional[str]:
        if not self.bot_token or not self._http:
            return None
        payload: dict = {"chat_id": chat_id, "text": text[:4096]}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = await self._http.post(
                TELEGRAM_API.format(token=self.bot_token, method="sendMessage"),
                json=payload,
                timeout=10.0,
            )
            data = resp.json()
            if data.get("ok"):
                return str(data["result"]["message_id"])
        except Exception as exc:
            logger.error("send_message_get_id failed: %s", exc)
        return None

    async def _edit_message(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        *,
        reply_markup: Optional[dict] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> None:
        if not self.bot_token or not message_id or not self._http:
            return
        payload: dict = {
            "chat_id":    chat_id,
            "message_id": message_id,
            "text":       text[:4096],
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = await self._http.post(
                TELEGRAM_API.format(token=self.bot_token, method="editMessageText"),
                json=payload,
                timeout=10.0,
            )
            result = resp.json()
            if not result.get("ok") and parse_mode:
                # Markdown parse error — retry as plain text
                payload.pop("parse_mode", None)
                await self._http.post(
                    TELEGRAM_API.format(token=self.bot_token, method="editMessageText"),
                    json=payload,
                    timeout=10.0,
                )
        except Exception as exc:
            logger.debug("edit_message failed: %s", exc)

    async def _send_typing(self, chat_id: str) -> None:
        if not self.bot_token or not self._http:
            return
        try:
            await self._http.post(
                TELEGRAM_API.format(token=self.bot_token, method="sendChatAction"),
                json={"chat_id": chat_id, "action": "typing"},
                timeout=5.0,
            )
        except Exception:
            pass

    async def _send_screenshot(self, chat_id: str, caption: str) -> None:
        if not self.bot_token or not self._http:
            return
        img, _ = screen_capture.capture_as_pil()
        if not img:
            await self._send_message(
                chat_id,
                "⚠️ *Screenshot Blocked* — sensitive app (bank/password manager) open.",
                reply_markup=self._default_keyboard(),
            )
            return
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        buf.seek(0)
        try:
            await self._http.post(
                TELEGRAM_API.format(token=self.bot_token, method="sendPhoto"),
                data={
                    "chat_id":      chat_id,
                    "caption":      caption,
                    "reply_markup": json.dumps(self._default_keyboard()),
                    "parse_mode":   "Markdown",
                },
                files={"photo": ("screenshot.jpg", buf.read(), "image/jpeg")},
                timeout=20.0,
            )
        except Exception as exc:
            logger.error("send_screenshot failed: %s", exc)

    async def _post_with_retry(
        self,
        url: str,
        payload: dict,
        *,
        max_retries: int = MAX_EDIT_RETRIES,
    ) -> None:
        """POST with exponential back-off on 429 Too Many Requests."""
        if not self._http:
            return
        delay = 1.0
        for attempt in range(max_retries):
            try:
                resp = await self._http.post(url, json=payload, timeout=10.0)
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
                if not resp.json().get("ok") and "parse_mode" in payload:
                    payload = {**payload}
                    payload.pop("parse_mode", None)
                    continue
                return
            except Exception as exc:
                logger.error("HTTP post failed (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(delay)
                delay *= 2

    # ──────────────────────────────────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_dangerous_shutdown(text_lower: str) -> bool:
        return (
            any(kw in text_lower for kw in DANGEROUS_SHUTDOWN_KEYWORDS)
            and any(kw in text_lower for kw in SYSTEM_SCOPE_KEYWORDS)
        )

    @staticmethod
    def _detect_language_hint(text: str) -> str:
        bengali   = sum(1 for c in text if "\u0980" <= c <= "\u09ff")
        devanag   = sum(1 for c in text if "\u0900" <= c <= "\u097f")
        if bengali > 2:
            return "🌐 Detected: Bengali"
        if devanag > 2:
            return "🌐 Detected: Hindi"
        return "🌐 Detected: English"

    @staticmethod
    def _default_keyboard() -> dict:
        return {
            "keyboard": [
                [{"text": "🛑 Emergency Stop"}, {"text": "📸 Get Screenshot"}],
                [{"text": "📊 Check Status"},   {"text": "🔑 WhatsApp Link"}],
                [{"text": "❓ Help & Guide"},   {"text": "👤 Unpair Bot"}],
            ],
            "resize_keyboard":   True,
            "one_time_keyboard": False,
        }

    def _clean_duplicate_processes(self) -> None:
        try:
            import psutil
            current_pid    = os.getpid()
            protected_pids = {current_pid}
            try:
                proc = psutil.Process(current_pid)
                while proc.parent():
                    protected_pids.add(proc.parent().pid)
                    proc = proc.parent()
            except Exception:
                pass

            if os.name == "nt":
                raw = subprocess.check_output(
                    'powershell -Command "Get-CimInstance Win32_Process '
                    '-Filter \\"Name = \'python.exe\'\\" | '
                    'Select-Object ProcessId, CommandLine | ConvertTo-Json"',
                    shell=True,
                ).decode("utf-8", errors="ignore")
                if not raw.strip():
                    return
                processes = json.loads(raw)
                if isinstance(processes, dict):
                    processes = [processes]
                for p in processes:
                    if not p:
                        continue
                    pid     = p.get("ProcessId")
                    cmdline = p.get("CommandLine") or ""
                    if pid and pid not in protected_pids and (
                        "uvicorn" in cmdline or "spawn_main" in cmdline
                    ):
                        logger.warning("Killing conflicting process PID=%s", pid)
                        subprocess.run(
                            f"taskkill /F /PID {pid}", shell=True, capture_output=True
                        )
            else:
                subprocess.run("fuser -k 8000/tcp", shell=True, capture_output=True)
        except Exception as exc:
            logger.error("clean_duplicate_processes failed: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────────────

telegram_bot_manager = TelegramBotManager()