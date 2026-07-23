import os
import asyncio
import socket
import subprocess
import logging
from typing import Optional
import httpx
import time
import uuid

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 16 * 1024
MAX_CAPTION_LENGTH = 4096


def _path_inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((path, root)) == root
    except (OSError, ValueError):
        return False


def validate_attachment_path(file_path: str) -> tuple[Optional[str], Optional[str]]:
    """Resolve and validate an attachment before starting the local service."""
    from backend.tools.unified.core.policy import is_safe_path, is_sensitive_path

    if not isinstance(file_path, str) or not file_path.strip():
        return None, "Attachment path is required"
    resolved = os.path.realpath(os.path.abspath(file_path))
    if not os.path.isfile(resolved):
        return None, "Attachment file does not exist"
    uploads = os.path.realpath(os.path.abspath("data/uploads"))
    if is_sensitive_path(resolved):
        return None, "Attachment path is protected"
    if not is_safe_path(resolved) and not _path_inside(resolved, uploads):
        return None, "Attachment path is protected"
    return resolved, None

class WhatsAppManager:
    def __init__(self):
        self.process = None
        self.log_file = None   # file handle for node.js service stdout/stderr
        self.api_key = self._get_or_create_key()
        self._startup_error = None

    def _get_or_create_key(self):
        import os
        import sys
        import tempfile
        import secrets
        import shutil
        import atexit
        import subprocess
        
        key_file = os.path.join(tempfile.gettempdir(), "maya_wa_key.tmp")
        
        # Cleanup on graceful exit without turning interpreter shutdown into an
        # error if another process or an ACL already removed/locked the file.
        def _cleanup_key_file():
            try:
                if os.path.exists(key_file):
                    os.remove(key_file)
            except OSError:
                pass

        atexit.register(_cleanup_key_file)
        
        try:
            if os.path.exists(key_file):
                with open(key_file, "r") as f:
                    return f.read().strip()
            
            new_key = secrets.token_hex(32)
            
            # Atomic write to prevent race conditions
            dir_name = os.path.dirname(key_file)
            with tempfile.NamedTemporaryFile(mode='w', dir=dir_name, delete=False) as tmp:
                tmp.write(new_key)
                tmp_path = tmp.name
            shutil.move(tmp_path, key_file)
            
            # Set restrictive permissions properly (Windows vs POSIX)
            if sys.platform == "win32" and os.getenv("MAYA_TESTING") != "1":
                username = os.environ.get("USERNAME", "")
                result = subprocess.run(
                    ["icacls", key_file, "/inheritance:r", "/grant:r", f"{username}:(R,W)"],
                    capture_output=True
                )
                if result.returncode != 0:
                    raise RuntimeError(f"Failed to set file permissions: {result.stderr.decode()}")
            else:
                os.chmod(key_file, 0o600)
                
            return new_key
        except Exception as e:
            logger.error("[WA] Key generation error: %s", type(e).__name__)
            return secrets.token_hex(32)

    def _get_headers(self):
        return {"x-api-key": self.api_key}

    def _normalize_phone(self, phone: str) -> str:
        if not isinstance(phone, str):
            return None
        clean_phone = "".join(c for c in phone if c.isdigit())
        if not clean_phone:
            return None
        if clean_phone.startswith("00"):
            clean_phone = clean_phone[2:]
        elif clean_phone.startswith("0"):
            clean_phone = clean_phone[1:]
        if len(clean_phone) == 10:
            clean_phone = "91" + clean_phone
        if not 10 <= len(clean_phone) <= 15 or set(clean_phone) == {"0"}:
            return None
        return clean_phone


    def _port_9001_is_listening(self) -> bool:
        """Return whether a local TCP listener owns the WhatsApp service port."""
        try:
            with socket.create_connection(("127.0.0.1", 9001), timeout=0.5):
                return True
        except OSError:
            return False

    def _close_log_file(self) -> None:
        if self.log_file is not None:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None

    def start(self) -> bool:
        """Start Maya's service without ever terminating another process."""
        if self.process:
            if self.process.poll() is None:
                self._startup_error = None
                return True
            self.process = None
            self._close_log_file()

        self._startup_error = None
        try:
            resp = httpx.get(
                "http://127.0.0.1:9001/status",
                timeout=1.5,
                headers=self._get_headers(),
            )
            if resp.status_code == 200:
                logger.info("WhatsApp service is already running on port 9001.")
                return True
            if resp.status_code in (401, 403):
                self._startup_error = (
                    "Port 9001 is occupied by a service that rejected Maya credentials."
                )
            else:
                self._startup_error = (
                    "Port 9001 is occupied by an incompatible local HTTP service."
                )
            logger.error("[WA] %s", self._startup_error)
            return False
        except Exception:
            if self._port_9001_is_listening():
                self._startup_error = "Port 9001 is occupied by another local service."
                logger.error("[WA] %s", self._startup_error)
                return False

        script_dir = os.path.dirname(os.path.abspath(__file__))
        service_dir = os.path.join(script_dir, "whatsapp_service")
        index_js = os.path.join(service_dir, "index.js")

        if not os.path.exists(index_js):
            self._startup_error = "WhatsApp service script was not found."
            logger.error("[WA] %s", self._startup_error)
            return False

        logger.info("Spawning WhatsApp Node.js service subprocess...")
        try:
            log_path = os.path.abspath(os.path.join(script_dir, "../../../../data/whatsapp_service.log"))
            self.log_file = open(log_path, "a", encoding="utf-8")
            env = os.environ.copy()
            env["WA_API_KEY"] = self.api_key
            self.process = subprocess.Popen(
                ["node", "index.js"],
                cwd=service_dir,
                stdout=self.log_file,
                stderr=self.log_file,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            time.sleep(1.5)
            if self.process.poll() is not None:
                self._startup_error = "WhatsApp service exited during startup."
                logger.error("[WA] %s", self._startup_error)
                self.process = None
                self._close_log_file()
                return False
            logger.info("WhatsApp Node.js service spawned successfully.")
            return True
        except Exception as e:
            self._startup_error = "WhatsApp service could not be started."
            logger.error("[WA] %s (%s)", self._startup_error, type(e).__name__)
            self.process = None
            self._close_log_file()
            return False

    def stop(self):
        process = self.process
        try:
            if process:
                logger.info("Terminating WhatsApp Node.js service...")
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                logger.info("WhatsApp Node.js service terminated.")
        except Exception as exc:
            logger.error(
                "[WA] WhatsApp service shutdown error: %s",
                type(exc).__name__,
            )
        finally:
            still_running = False
            if process is not None:
                try:
                    still_running = process.poll() is None
                except Exception:
                    still_running = True
            self.process = process if still_running else None
            # Prevent descriptor leaks across repeated integration toggles.
            self._close_log_file()

    def get_status(self) -> dict:
        """Check status, retrying up to 3 times to handle brief reconnect windows."""
        if self._startup_error:
            return {"status": "disconnected", "error": self._startup_error}
        for attempt in range(3):
            try:
                resp = httpx.get("http://127.0.0.1:9001/status", timeout=3.0, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") in ["connected", "authenticated"]:
                        return data
                    # Not connected yet — wait briefly and retry
                    if attempt < 2:
                        time.sleep(2)
            except Exception:
                if attempt < 2:
                    time.sleep(2)
        return {"status": "disconnected"}

    def wait_for_connected(self, timeout_seconds: int = 90) -> bool:
        """Poll until WhatsApp is 'connected' or 'authenticated' (both can send). Returns True if ready within timeout."""
        if self._startup_error:
            logger.error("[WA] Cannot wait for WhatsApp: %s", self._startup_error)
            return False
        deadline = time.time() + timeout_seconds
        poll_count = 0
        while time.time() < deadline:
            try:
                resp = httpx.get("http://127.0.0.1:9001/status", timeout=3.0, headers=self._get_headers())
                if resp.status_code == 200:
                    status = resp.json().get("status", "")
                    if status in ("connected", "authenticated"):
                        if poll_count > 0:
                            logger.info(f"[WA] WhatsApp is ready to send (status={status}).")
                        return True
                    if poll_count == 0:
                        logger.info(f"[WA] Waiting for WhatsApp (current status: {status})...")
            except Exception:
                pass
            time.sleep(2)
            poll_count += 1
        logger.warning(f"[WA] Timed out waiting for WhatsApp after {timeout_seconds}s")
        return False

    def send_message(self, phone: str, message: str) -> bool:
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            logger.error("[WA] Invalid recipient phone number.")
            return False
        if not isinstance(message, str) or not message or len(message) > MAX_MESSAGE_LENGTH:
            logger.error("[WA] Message must contain 1-%d characters.", MAX_MESSAGE_LENGTH)
            return False
        # Auto-ensure process is started
        if not self.start():
            logger.error("[WA] Cannot send message: %s", self._startup_error)
            return False
        # Wait for WhatsApp to be fully ready (handles post-startup sync delay)
        if not self.wait_for_connected():
            logger.error("[WA] Cannot send message: WhatsApp timed out waiting for ready state.")
            return False
        
        request_id = str(uuid.uuid4())
        for attempt in range(3):
            try:
                payload = {"to": clean_phone, "message": message, "requestId": request_id}
                resp = httpx.post("http://127.0.0.1:9001/send", json=payload, timeout=90.0, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        logger.info("Successfully sent WhatsApp message to ...%s", clean_phone[-4:])
                        return True
                elif 400 <= resp.status_code < 500:
                    try:
                        error = str(resp.json().get("error", "request rejected"))
                    except Exception:
                        error = "request rejected"
                    if "not connected" not in error.lower():
                        logger.warning("[WA] Send rejected with HTTP %s", resp.status_code)
                        return False
                    # WhatsApp not connected — wait and retry
                    logger.warning(f"WhatsApp not connected (attempt {attempt+1}), waiting...")
                    if attempt < 2:
                        time.sleep(3)
            except Exception as e:
                logger.error(
                    "Error sending WhatsApp message (attempt %d): %s",
                    attempt + 1,
                    type(e).__name__,
                )
                if attempt < 2:
                    time.sleep(2)
            
        return False

    def send_message_receipt(self, phone: str, message: str) -> dict:
        """Send text and return only the transport state actually observed."""
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            return {"success": False, "message_id": None, "status": "unknown", "error": "Invalid phone number"}
        if not isinstance(message, str) or not message or len(message) > MAX_MESSAGE_LENGTH:
            return {"success": False, "message_id": None, "status": "unknown", "error": "Message must contain text"}
        if not self.start():
            return {
                "success": False,
                "message_id": None,
                "status": "unknown",
                "error": self._startup_error or "WhatsApp service failed to start",
            }
        if not self.wait_for_connected():
            return {
                "success": False,
                "message_id": None,
                "status": "unknown",
                "error": "WhatsApp is not connected (timed out waiting for ready state)",
            }

        request_id = str(uuid.uuid4())
        last_error = "WhatsApp did not accept the message"
        for attempt in range(3):
            try:
                response = httpx.post(
                    "http://127.0.0.1:9001/send",
                    json={"to": clean_phone, "message": message, "requestId": request_id},
                    timeout=90.0,
                    headers=self._get_headers(),
                )
                try:
                    data = response.json()
                except Exception:
                    data = {}
                if response.status_code == 200 and data.get("success"):
                    return {
                        "success": True,
                        "message_id": data.get("messageId"),
                        "status": data.get("status") or "sent",
                        "deduplicated": bool(data.get("deduplicated")),
                        "error": None,
                    }
                last_error = str(data.get("error") or f"HTTP {response.status_code}")
                if 400 <= response.status_code < 500 and "not connected" not in last_error.lower():
                    return {"success": False, "message_id": None, "status": "unknown", "error": last_error}
            except Exception as exc:
                last_error = type(exc).__name__
            if attempt < 2:
                time.sleep(2)
        return {"success": False, "message_id": None, "status": "unknown", "error": last_error}

    def revoke_messages(self, phone: str, count: int = 1) -> bool:
        """Revokes (Deletes for Everyone) the most recent messages sent by you to a specific phone number."""
        if not self.start():
            logger.error("[WA] Cannot revoke message: %s", self._startup_error)
            return False
        if not self.wait_for_connected():
            logger.error("[WA] Cannot revoke message: WhatsApp timed out waiting for ready state.")
            return False
            
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            logger.error("[WA] Invalid recipient phone number.")
            return False
            
        to_chat_id = f"{clean_phone}@c.us"
        try:
            payload = {"toChatId": to_chat_id, "count": count}
            resp = httpx.post("http://127.0.0.1:9001/revoke", json=payload, timeout=90.0, headers=self._get_headers())
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    revoked = data.get("revoked", 0)
                    logger.info(
                        "Successfully revoked %d WhatsApp message(s) for ...%s",
                        revoked,
                        clean_phone[-4:],
                    )
                    return True
        except Exception as e:
            logger.error("Error revoking WhatsApp messages: %s", type(e).__name__)
            
        return False

    def revoke_messages_receipt(self, phone: str, count: int = 1) -> dict:
        """Request delete-for-everyone and report the exact accepted count."""
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            return {"success": False, "revoked": 0, "error": "Invalid phone number"}
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 50:
            return {"success": False, "revoked": 0, "error": "Count must be between 1 and 50"}
        if not self.start():
            return {"success": False, "revoked": 0, "error": self._startup_error or "WhatsApp service failed to start"}
        if not self.wait_for_connected():
            return {"success": False, "revoked": 0, "error": "WhatsApp is not connected (timed out waiting for ready state)"}

        try:
            response = httpx.post(
                "http://127.0.0.1:9001/revoke",
                json={"toChatId": f"{clean_phone}@c.us", "count": count},
                timeout=90.0,
                headers=self._get_headers(),
            )
            try:
                data = response.json()
            except Exception:
                data = {}
            revoked = data.get("revoked", 0)
            if response.status_code == 200 and data.get("success") and isinstance(revoked, int) and revoked > 0:
                return {"success": True, "revoked": revoked, "error": None}
            return {
                "success": False,
                "revoked": 0,
                "error": str(data.get("error") or f"HTTP {response.status_code}"),
            }
        except Exception as exc:
            logger.error("Error revoking WhatsApp messages: %s", type(exc).__name__)
            return {"success": False, "revoked": 0, "error": type(exc).__name__}

    def get_pairing_code(self, phone: str) -> Optional[str]:
        # Auto-ensure process is started
        if not self.start():
            return None
        
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            logger.error("[WA] Invalid phone format for pairing.")
            return None
            
        try:
            resp = httpx.get(f"http://127.0.0.1:9001/pair-code?phone={clean_phone}", timeout=30.0, headers=self._get_headers())
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("code")
        except Exception as e:
            logger.error(
                "Error requesting pairing code from service: %s",
                type(e).__name__,
            )
            
        return None

    def send_file(self, phone: str, file_path: str, caption: str = "") -> dict:
        """Send one validated attachment with idempotent transport retries."""
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            return {"success": False, "message_id": None, "error": "Invalid phone number"}
        if not isinstance(caption, str) or len(caption) > MAX_CAPTION_LENGTH:
            return {"success": False, "message_id": None, "error": f"Caption exceeds {MAX_CAPTION_LENGTH} characters"}
        file_path, path_error = validate_attachment_path(file_path)
        if path_error:
            return {"success": False, "message_id": None, "error": path_error}

        if not self.start():
            return {
                "success": False,
                "message_id": None,
                "error": self._startup_error or "WhatsApp service failed to start",
            }
        if not self.wait_for_connected():
            return {"success": False, "message_id": None, "error": "WhatsApp is not connected (timed out waiting for ready state)."}

        request_id = str(uuid.uuid4())
        last_error = "Unknown error"
        for attempt in range(3):
            try:
                payload = {"to": clean_phone, "filePath": file_path, "caption": caption, "requestId": request_id}
                resp = httpx.post("http://127.0.0.1:9001/send-file", json=payload, timeout=90.0, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        logger.info("File sent to ...%s: %s", clean_phone[-4:], os.path.basename(file_path))
                        return {"success": True, "message_id": data.get("messageId"), "error": None}
                try:
                    last_error = str(resp.json().get("error", "Unknown error"))
                except Exception:
                    last_error = f"HTTP {resp.status_code}"
                logger.warning(
                    "send_file attempt %d failed with HTTP %s",
                    attempt + 1,
                    resp.status_code,
                )
                if 400 <= resp.status_code < 500 and "not connected" not in last_error.lower():
                    return {"success": False, "message_id": None, "error": last_error}
                if attempt < 2:
                    time.sleep(2)
            except Exception as e:
                last_error = str(e)
                logger.error(
                    "send_file error (attempt %d): %s",
                    attempt + 1,
                    type(e).__name__,
                )
                if attempt < 2:
                    time.sleep(2)
        return {"success": False, "message_id": None, "error": last_error}

    def send_files(self, phone: str, files: list) -> list:
        """Send a validated attachment batch with one idempotency key."""
        if not isinstance(files, list) or not 1 <= len(files) <= 10:
            return [{"file": "?", "success": False, "error": "Provide between 1 and 10 files"}]
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            return [{"file": "?", "success": False, "error": "Invalid phone"}]

        validated = []
        validation_errors = []
        seen_paths = set()
        for item in files:
            if not isinstance(item, dict):
                validation_errors.append({"file": "?", "success": False, "error": "Invalid attachment entry"})
                continue
            resolved, error = validate_attachment_path(item.get("filePath"))
            caption = item.get("caption", "")
            if error:
                validation_errors.append({"file": item.get("filePath", "?"), "success": False, "error": error})
            elif not isinstance(caption, str) or len(caption) > MAX_CAPTION_LENGTH:
                validation_errors.append({"file": resolved, "success": False, "error": f"Caption exceeds {MAX_CAPTION_LENGTH} characters"})
            elif resolved in seen_paths:
                validation_errors.append({"file": resolved, "success": False, "error": "Duplicate attachment path"})
            else:
                seen_paths.add(resolved)
                validated.append({"filePath": resolved, "caption": caption})
        if validation_errors:
            return validation_errors

        if not self.start():
            error = self._startup_error or "WhatsApp service failed to start"
            return [
                {"file": f["filePath"], "success": False, "error": error}
                for f in validated
            ]
        if not self.wait_for_connected():
            return [{"file": f["filePath"], "success": False, "error": "WhatsApp is not connected"} for f in validated]

        request_id = str(uuid.uuid4())
        last_error = "Unknown error"
        for attempt in range(3):
            try:
                payload = {"to": clean_phone, "files": validated, "requestId": request_id}
                resp = httpx.post("http://127.0.0.1:9001/send-files", json=payload, timeout=120.0, headers=self._get_headers())
                if resp.status_code == 200:
                    return resp.json().get("results", [])
                try:
                    last_error = str(resp.json().get("error", "Unknown error"))
                except Exception:
                    last_error = f"HTTP {resp.status_code}"
                if 400 <= resp.status_code < 500 and "not connected" not in last_error.lower():
                    break
            except Exception as e:
                last_error = str(e)
            if attempt < 2:
                time.sleep(2)
        return [{"file": f["filePath"], "success": False, "error": last_error} for f in validated]

    def get_message_status(self, message_id: str) -> str:
        """
        Returns delivery status of a sent message.
        Possible values: 'sent', 'delivered', 'read', 'played', 'pending', 'unknown'
        """
        try:
            resp = httpx.get(f"http://127.0.0.1:9001/message-status?messageId={message_id}", timeout=5.0, headers=self._get_headers())
            if resp.status_code == 200:
                return resp.json().get("status", "unknown")
        except Exception as e:
            logger.error("get_message_status error: %s", type(e).__name__)
        return "unknown"


    def fetch_messages(self, phone: str, limit: int = None) -> dict:
        import os
        if not self.start():
            return {
                "success": False,
                "error": self._startup_error or "WhatsApp service failed to start.",
            }
        if not self.wait_for_connected():
            return {"success": False, "error": "WhatsApp is not connected."}
            
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            return {"success": False, "error": "Invalid phone format"}
            
        effective_limit = limit or int(os.getenv("WHATSAPP_MSG_LIMIT", "10"))
        
        try:
            logger.debug(f"[WA] Fetching messages for ...{clean_phone[-4:]}")
            resp = httpx.get(
                f"http://127.0.0.1:9001/fetch-messages",
                params={"phone": clean_phone, "limit": effective_limit},
                headers=self._get_headers(),
                timeout=10.0
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                return {"success": False, "error": resp.json().get("error", "Unknown error")}
        except Exception as e:
            logger.error("[WA] fetch_messages error: %s", type(e).__name__)
            return {"success": False, "error": str(e)}

    # ───────────────────────────────────────────────────────────────────
    # Incoming Message Listener (for WhatsApp Read + Reply)

    # ───────────────────────────────────────────────────────────────────

    async def poll_triggered(self, client: httpx.AsyncClient = None) -> list:
        """
        Drain the Node.js triggered queue.
        Returns a list of incoming message dicts, or [] on error.
        Raises exceptions to be handled by the caller.
        """
        try:
            if client:
                resp = await client.get("http://127.0.0.1:9001/poll-triggered", headers=self._get_headers(), timeout=5.0)
                if resp.status_code == 200:
                    return resp.json().get("items", [])
            else:
                async with httpx.AsyncClient() as temp_client:
                    resp = await temp_client.get("http://127.0.0.1:9001/poll-triggered", headers=self._get_headers(), timeout=5.0)
                    if resp.status_code == 200:
                        return resp.json().get("items", [])
        except Exception as e:
            raise e
        return []

    async def start_incoming_listener(self, callback) -> None:
        """
        Polls /poll-triggered every 2 seconds.
        Calls await callback(item) for each new incoming message.
        Maintains a single HTTP client and properly handles cancellation.
        """
        logger.info("[WA] Incoming message listener started (polling every 2s).")
        base_interval = 2.0
        max_backoff = 60.0
        consecutive_errors = 0

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                while True:
                    try:
                        items = await self.poll_triggered(client)
                        for item in items:
                            try:
                                await callback(item)
                            except Exception as cb_err:
                                logger.error(
                                    "[WA] Error in incoming message callback: %s",
                                    type(cb_err).__name__,
                                )

                        if consecutive_errors:
                            logger.info(
                                "[WA] Polling recovered after %d error(s).",
                                consecutive_errors,
                            )
                        consecutive_errors = 0  # reset on success
                        sleep_for = base_interval
                    except asyncio.CancelledError:
                        raise  # Always propagate cancellation
                    except Exception as e:
                        consecutive_errors += 1
                        # Back off exponentially so a downed Node.js service
                        # does not get hammered, but never stop the loop —
                        # it must self-recover once the service returns.
                        sleep_for = min(base_interval * (2 ** consecutive_errors), max_backoff)
                        log = logger.warning if consecutive_errors >= 5 else logger.debug
                        log(
                            "[WA] poll_triggered error (attempt %d, retrying in %.0fs): %s",
                            consecutive_errors,
                            sleep_for,
                            type(e).__name__,
                        )

                    await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            logger.info("[WA] Incoming listener cancelled.")
            raise

    def reply_to_chat(self, chat_id: str, message: str) -> bool:
        """
        Send a reply to a specific WhatsApp chatId (works for both
        private chats xxx@c.us and groups xxx@g.us).
        """
        try:
            resp = httpx.post(
                "http://127.0.0.1:9001/reply",
                json={"chatId": chat_id, "message": message},
                timeout=30.0
            , headers=self._get_headers())
            if resp.status_code == 200 and resp.json().get("success"):
                logger.info("[WA] Reply sent successfully.")
                return True
            logger.warning("[WA] reply_to_chat failed with HTTP %s", resp.status_code)
        except Exception as e:
            logger.error("[WA] reply_to_chat error: %s", type(e).__name__)
        return False

    def resolve_contact(self, name: str, wait_timeout: int = 90) -> dict:
        """Search WhatsApp synced contacts by name and return {name, number}."""
        if not self.start():
            return {
                "success": False,
                "error": self._startup_error or "WhatsApp service failed to start.",
            }
        if not self.wait_for_connected(wait_timeout):
            return {"success": False, "error": "WhatsApp is not connected."}

        try:
            resp = httpx.get(
                f"http://127.0.0.1:9001/resolve-contact",
                params={"name": name},
                timeout=10.0,
                headers=self._get_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return {
                        "success": True,
                        "name": data.get("name", name),
                        "phone": data.get("number"),
                        "candidates": data.get("candidates", []),
                    }
                return {"success": False, "error": data.get("error", "Unknown error")}
            else:
                return {"success": False, "error": resp.json().get("error", f"HTTP {resp.status_code}")}
        except Exception as e:
            logger.error("[WA] resolve_contact error: %s", type(e).__name__)
            return {"success": False, "error": str(e)}


    def register_known_sender(self, number: str) -> bool:
        """Allow-list a WhatsApp sender in the Node.js service for this session."""
        clean_number = self._normalize_phone(number)
        if not clean_number:
            return False
        try:
            resp = httpx.post(
                "http://127.0.0.1:9001/register-known",
                json={"number": clean_number},
                timeout=5.0,
                headers=self._get_headers(),
            )
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception as e:
            logger.error(
                "[WA] register_known_sender error: %s",
                type(e).__name__,
            )
            return False


    def block_sender(self, number: str) -> bool:
        """Block a phone number in the Node.js service (persists for session)."""
        clean_number = self._normalize_phone(number)
        if not clean_number:
            return False
        try:
            resp = httpx.post(
                "http://127.0.0.1:9001/block-number",
                json={"number": clean_number},
                timeout=5.0,
                headers=self._get_headers(),
            )
            return resp.status_code == 200 and resp.json().get("success", False)
        except Exception as e:
            logger.error("[WA] block_sender error: %s", type(e).__name__)
            return False


whatsapp_manager = WhatsAppManager()
