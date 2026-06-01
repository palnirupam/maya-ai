import os
import asyncio
import subprocess
import logging
from typing import Optional
import httpx
import time

logger = logging.getLogger(__name__)

class WhatsAppManager:
    def __init__(self):
        self.process = None
        self.api_key = self._get_or_create_key()

    def _get_or_create_key(self):
        import os
        import sys
        import tempfile
        import secrets
        import shutil
        import atexit
        import subprocess
        
        key_file = os.path.join(tempfile.gettempdir(), "maya_wa_key.tmp")
        
        # Cleanup on graceful exit
        atexit.register(lambda: os.remove(key_file) if os.path.exists(key_file) else None)
        
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
            if sys.platform == "win32":
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
            logger.error(f"[WA] Key generation error: {e}")
            return secrets.token_hex(32)

    def _get_headers(self):
        return {"x-api-key": self.api_key}

    def _normalize_phone(self, phone: str) -> str:
        clean_phone = "".join(c for c in phone if c.isdigit())
        if not clean_phone:
            return None
        if clean_phone.startswith("00"):
            clean_phone = clean_phone[2:]
        elif clean_phone.startswith("0"):
            clean_phone = clean_phone[1:]
        if len(clean_phone) == 10:
            clean_phone = "91" + clean_phone
        return clean_phone


    def _kill_port_9001(self):
        try:
            if os.name == 'nt':
                # 1. Proactively kill any node process running the WhatsApp service index.js
                import json
                try:
                    cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"Name = \'node.exe\'\\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"'
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
                            if pid and "index.js" in cmdline:
                                logger.info(f"Killing duplicate node process running WhatsApp service with PID {pid}...")
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                except Exception as pe:
                    logger.error(f"Failed to kill index.js node processes via PowerShell: {pe}")

                # 2. Check traditional netstat for port 9001 listening
                output = subprocess.check_output("netstat -ano", shell=True).decode('utf-8', errors='ignore')
                for line in output.splitlines():
                    if ":9001" in line and "LISTENING" in line:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pid = parts[-1]
                            if pid.isdigit() and pid != '0':
                                logger.info(f"Found stale WhatsApp process with PID {pid} on port 9001, killing it...")
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
            else:
                # Unix fallback
                subprocess.run("fuser -k 9001/tcp", shell=True, capture_output=True)
        except Exception as e:
            logger.error(f"Failed to kill stale process on port 9001: {e}")

    def start(self):
        if self.process and self.process.poll() is None:
            return
            
        # Smart Check: If the service is already running and connected/authenticated, do not restart it
        try:
            resp = httpx.get("http://127.0.0.1:9001/status", timeout=1.5, headers=self._get_headers())
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") in ("connected", "authenticated"):
                    logger.info("WhatsApp service is already running and active on port 9001.")
                    return
        except Exception:
            pass
            
        # Proactively kill any orphaned node processes listening on port 9001
        self._kill_port_9001()
            
        script_dir = os.path.dirname(os.path.abspath(__file__))
        service_dir = os.path.join(script_dir, "whatsapp_service")
        index_js = os.path.join(service_dir, "index.js")
        
        if not os.path.exists(index_js):
            logger.error(f"WhatsApp service script not found at: {index_js}")
            return
            
        logger.info("Spawning WhatsApp Node.js service subprocess...")
        try:
            # Spawn Node.js background process and write stdout/stderr to a log file
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
            time.sleep(1.5) # Allow it to bind port
            logger.info("WhatsApp Node.js service spawned successfully.")
        except Exception as e:
            logger.error(f"Failed to spawn WhatsApp service: {e}")

    def stop(self):
        if self.process:
            logger.info("Terminating WhatsApp Node.js service...")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            logger.info("WhatsApp Node.js service terminated.")

    def get_status(self) -> dict:
        """Check status, retrying up to 3 times to handle brief reconnect windows."""
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

    def wait_for_connected(self, timeout_seconds: int = 30) -> bool:
        """Poll until WhatsApp is 'connected' or 'authenticated' (both can send). Returns True if ready within timeout."""
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
        # Auto-ensure process is started
        self.start()
        # Wait for WhatsApp to be fully ready (handles post-startup sync delay)
        if not self.wait_for_connected():
            logger.error("[WA] Cannot send message: WhatsApp timed out waiting for ready state.")
            return False
        
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            logger.error(f"Invalid phone format: {phone}")
            return False
            
        # Retry send up to 3 times in case of transient disconnect
        for attempt in range(3):
            try:
                payload = {"to": clean_phone, "message": message}
                resp = httpx.post("http://127.0.0.1:9001/send", json={"to": clean_phone, "message": message}, timeout=90.0, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        logger.info(f"Successfully sent WhatsApp message to {clean_phone}")
                        return True
                elif resp.status_code == 400:
                    # WhatsApp not connected — wait and retry
                    logger.warning(f"WhatsApp not connected (attempt {attempt+1}), waiting...")
                    if attempt < 2:
                        time.sleep(3)
            except Exception as e:
                logger.error(f"Error sending WhatsApp message (attempt {attempt+1}): {e}")
                if attempt < 2:
                    time.sleep(2)
            
        return False

    def revoke_messages(self, phone: str, count: int = 1) -> bool:
        """Revokes (Deletes for Everyone) the most recent messages sent by you to a specific phone number."""
        self.start()
        if not self.wait_for_connected():
            logger.error("[WA] Cannot revoke message: WhatsApp timed out waiting for ready state.")
            return False
            
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            logger.error(f"Invalid phone format: {phone}")
            return False
            
        to_chat_id = f"{clean_phone}@c.us"
        try:
            payload = {"toChatId": to_chat_id, "count": count}
            resp = httpx.post("http://127.0.0.1:9001/revoke", json=payload, timeout=90.0, headers=self._get_headers())
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    revoked = data.get("revoked", 0)
                    logger.info(f"Successfully revoked {revoked} WhatsApp message(s) for {clean_phone}")
                    return True
        except Exception as e:
            logger.error(f"Error revoking WhatsApp messages: {e}")
            
        return False

    def get_pairing_code(self, phone: str) -> Optional[str]:
        # Auto-ensure process is started
        self.start()
        
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            logger.error(f"Invalid phone format for pairing: {phone}")
            return None
            
        try:
            resp = httpx.get(f"http://127.0.0.1:9001/pair-code?phone={clean_phone}", timeout=30.0, headers=self._get_headers())
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("code")
        except Exception as e:
            logger.error(f"Error requesting pairing code from service: {e}")
            
        return None

    def send_file(self, phone: str, file_path: str, caption: str = "") -> dict:
        """
        Sends a single file (image, PDF, video, audio, document) via WhatsApp.
        Returns dict: { "success": bool, "message_id": str | None, "error": str | None }
        """
        self.start()
        # Wait for WhatsApp to be fully ready (handles post-startup sync delay)
        if not self.wait_for_connected():
            return {"success": False, "message_id": None, "error": "WhatsApp is not connected (timed out waiting for ready state)."}
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            return {"success": False, "message_id": None, "error": "Invalid phone number"}

        for attempt in range(3):
            try:
                payload = {"to": clean_phone, "filePath": file_path, "caption": caption}
                resp = httpx.post("http://127.0.0.1:9001/send-file", json=payload, timeout=90.0, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        logger.info(f"File sent to {clean_phone}: {file_path} (msgId={data.get('messageId')})")
                        return {"success": True, "message_id": data.get("messageId"), "error": None}
                error_msg = resp.json().get("error", "Unknown error")
                logger.warning(f"send_file attempt {attempt+1} failed: {error_msg}")
                if attempt < 2:
                    time.sleep(2)
            except Exception as e:
                logger.error(f"send_file error (attempt {attempt+1}): {e}")
                if attempt < 2:
                    time.sleep(2)
        return {"success": False, "message_id": None, "error": "Failed after 3 attempts"}

    def send_files(self, phone: str, files: list) -> list:
        """
        Sends multiple files in sequence to a single recipient.
        files: list of {"filePath": str, "caption": str (optional)}
        Returns: list of {"file": str, "success": bool, "messageId": str, "error": str}
        """
        self.start()
        # Wait for WhatsApp to be fully ready (handles post-startup sync delay)
        if not self.wait_for_connected():
            return [{"file": f.get("filePath","?"), "success": False, "error": "WhatsApp is not connected (timed out waiting for ready state)."} for f in files]
            
        clean_phone = self._normalize_phone(phone)
        if not clean_phone:
            return [{"file": f.get("filePath","?"), "success": False, "error": "Invalid phone"} for f in files]

        try:
            payload = {"to": clean_phone, "files": files}
            resp = httpx.post("http://127.0.0.1:9001/send-files", json=payload, timeout=120.0, headers=self._get_headers())
            if resp.status_code == 200:
                return resp.json().get("results", [])
            logger.error(f"send_files failed: {resp.text}")
            return [{"file": f.get("filePath","?"), "success": False, "error": resp.json().get("error","Unknown")} for f in files]
        except Exception as e:
            logger.error(f"send_files error: {e}")
            return [{"file": f.get("filePath","?"), "success": False, "error": str(e)} for f in files]

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
            logger.error(f"get_message_status error: {e}")
        return "unknown"


    def fetch_messages(self, phone: str, limit: int = None) -> dict:
        import os
        self.start()
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
            logger.error(f"[WA] fetch_messages error: {e}")
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
                                logger.error(f"[WA] Error in incoming message callback: {cb_err}")
                        
                        consecutive_errors = 0  # reset on success
                    except asyncio.CancelledError:
                        raise  # Always propagate cancellation
                    except Exception as e:
                        consecutive_errors += 1
                        logger.debug(f"[WA] poll_triggered error (attempt {consecutive_errors}): {e}")
                        if consecutive_errors >= 5:
                            logger.error("[WA] Too many polling errors, exiting listener loop.")
                            break
                            
                    await asyncio.sleep(2.0)
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
                logger.info(f"[WA] Reply sent to chatId={chat_id}")
                return True
            logger.warning(f"[WA] reply_to_chat failed: {resp.text}")
        except Exception as e:
            logger.error(f"[WA] reply_to_chat error: {e}")
        return False

    def register_known_sender(self, number: str) -> bool:
        """Mark a phone number as known/approved in the Node.js service."""
        try:
            resp = httpx.post(
                "http://127.0.0.1:9001/register-known",
                json={"number": number},
                timeout=5.0
            , headers=self._get_headers())
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"[WA] register_known_sender error: {e}")
            return False

    def block_sender(self, number: str) -> bool:
        """Block a phone number in the Node.js service (persists for session)."""
        try:
            resp = httpx.post(
                "http://127.0.0.1:9001/block-number",
                json={"number": number},
                timeout=5.0
            , headers=self._get_headers())
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"[WA] block_sender error: {e}")
            return False


whatsapp_manager = WhatsAppManager()
