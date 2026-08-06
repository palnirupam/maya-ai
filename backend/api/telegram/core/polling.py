"""
polling.py
==========
Core polling manager for Telegram Bot API.

Handles:
- Long-polling with getUpdates API
- Update deduplication via rolling window
- Network error recovery with exponential backoff
- 409 conflict detection (duplicate bot instances)
- Dispatching updates to message/callback handlers
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
from typing import TYPE_CHECKING, Callable, Coroutine, Optional

import httpx

if TYPE_CHECKING:
    from backend.api.telegram.manager import TelegramBotManager

logger = logging.getLogger(__name__)

# Telegram Bot API endpoint template
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class PollingManager:
    """
    Manages the long-polling loop for receiving Telegram updates.
    
    Features:
    - Persistent HTTP connection reuse
    - Duplicate update filtering with rolling window (2048 entries)
    - Exponential backoff on network errors
    - 409 conflict handling (duplicate processes)
    - Automatic retry on transient failures
    """

    def __init__(self, manager: TelegramBotManager) -> None:
        """
        Initialize the polling manager.
        
        Args:
            manager: Parent TelegramBotManager instance for config and handlers
        """
        self.manager = manager
        
        # Deduplication: rolling window of seen update IDs
        # Use both deque (for FIFO eviction) and set (for O(1) lookup)
        self._seen_update_ids: deque[int] = deque(maxlen=2048)
        self._seen_update_id_set: set[int] = set()

    def _claim_update(self, update_id: int) -> bool:
        """
        Check if this update is new and claim it for processing.
        
        Returns False if we've already seen this update_id (duplicate),
        True if it's new and should be processed.
        
        Args:
            update_id: Telegram update ID from getUpdates response
            
        Returns:
            bool: True if update is new, False if already seen
        """
        if update_id in self._seen_update_id_set:
            return False
        
        # If deque is full, remove oldest entry from set
        if len(self._seen_update_ids) == self._seen_update_ids.maxlen:
            oldest = self._seen_update_ids.popleft()
            self._seen_update_id_set.discard(oldest)
        
        # Add new update_id to both structures
        self._seen_update_ids.append(update_id)
        self._seen_update_id_set.add(update_id)
        return True

    async def poll_loop(self) -> None:
        """
        Main long-polling loop.
        
        Continuously fetches updates from Telegram using getUpdates API:
        - 20-second long-polling timeout per request
        - Automatic offset management for sequential updates
        - Exponential backoff on errors (1s → 2s → 4s → ... → 60s max)
        - Handles 401 (invalid token), 409 (conflict), and network errors
        - Dispatches message/callback_query updates to appropriate handlers
        
        Runs until self.manager.running becomes False or task is cancelled.
        """
        offset: Optional[int] = None
        retry_delay = 1.0

        while self.manager.running:
            # Wait if bot not configured
            if not self.manager.bot_token or not self.manager._http:
                await asyncio.sleep(5.0)
                continue

            try:
                # Build request parameters
                params: dict = {"timeout": 20}
                if offset:
                    params["offset"] = offset

                # Long-poll for updates
                resp = await self.manager._http.get(
                    TELEGRAM_API.format(
                        token=self.manager.bot_token,
                        method="getUpdates"
                    ),
                    params=params,
                )
                
                # Reset retry delay on successful request
                retry_delay = 1.0

                if resp.status_code == 200:
                    # Process all updates in batch
                    for update in resp.json().get("result", []):
                        # Check for duplicate FIRST, before advancing offset
                        if not self._claim_update(update["update_id"]):
                            logger.info(
                                "[PollingManager] Ignoring duplicate update_id=%s",
                                update["update_id"],
                            )
                            continue
                        
                        # Only advance offset AFTER successful claim
                        offset = update["update_id"] + 1
                        
                        # Dispatch callback_query (inline button presses)
                        if cq := update.get("callback_query"):
                            task = asyncio.create_task(
                                self._safe_handle_callback(cq)
                            )
                            self.manager._track_background_task(task)
                        
                        # Dispatch message (text/media)
                        elif msg := update.get("message"):
                            task = asyncio.create_task(
                                self._safe_handle_message(msg)
                            )
                            self.manager._track_background_task(task)

                elif resp.status_code == 401:
                    # Invalid bot token - cannot recover
                    logger.error(
                        "[PollingManager] Bot token invalid (401). Stopping poll."
                    )
                    self.manager.running = False

                elif resp.status_code == 409:
                    # Conflict: another bot instance is polling with same token
                    logger.warning(
                        "[PollingManager] Telegram 409 Conflict — "
                        "cleaning duplicate processes."
                    )
                    self._clean_duplicate_processes()
                    await asyncio.sleep(5.0)

                else:
                    # Other HTTP errors (rate limit, server error, etc.)
                    logger.warning(
                        "[PollingManager] Telegram API returned %s",
                        resp.status_code
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60.0)

            except asyncio.CancelledError:
                # Clean shutdown requested
                logger.info("[PollingManager] Poll loop cancelled.")
                break

            except Exception as e:
                logger.error(
                    "[PollingManager] Unexpected error in poll loop: %s",
                    e, exc_info=True
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60.0)

    async def _safe_handle_message(self, message: dict) -> None:
        """Wrapper with error handling for message handler."""
        try:
            await self.manager._handle_message(message)
        except Exception as e:
            logger.error(
                "[PollingManager] Error handling message: %s",
                e, exc_info=True
            )
            # Try to notify user if we have chat_id
            try:
                chat_id = message.get("chat", {}).get("id")
                if chat_id:
                    await self.manager._send_message(
                        str(chat_id),
                        "⚠️ *Error processing message.* Please try again."
                    )
            except Exception:
                pass  # Don't fail if we can't send error message

    async def _safe_handle_callback(self, callback: dict) -> None:
        """Wrapper with error handling for callback handler."""
        try:
            await self.manager._handle_callback_query(callback)
        except Exception as e:
            logger.error(
                "[PollingManager] Error handling callback: %s",
                e, exc_info=True
            )

    def _clean_duplicate_processes(self) -> None:
        """
        Attempt to kill duplicate Python processes polling the same bot.
        
        Called when Telegram API returns 409 Conflict, indicating another
        bot instance is already receiving updates with this token.
        
        Implementation:
        - On Windows: Uses PowerShell to enumerate python.exe processes
        - Protects current process and its ancestors from termination
        - Kills processes containing 'telegram_bot' in command line
        - Fallback: Logs warning if psutil not available
        
        Note: This is a best-effort cleanup. If it fails, the 409 will
        persist until the conflicting process stops naturally.
        """
        try:
            import psutil
            import os
            import subprocess
        except ImportError:
            logger.warning(
                "[PollingManager] psutil not available, "
                "cannot clean duplicate processes"
            )
            return

        try:
            # Protect current process and all ancestors (uvicorn, shell, etc.)
            current_pid = os.getpid()
            protected_pids = {current_pid}
            
            try:
                proc = psutil.Process(current_pid)
                while proc.parent():
                    protected_pids.add(proc.parent().pid)
                    proc = proc.parent()
            except Exception:
                # Parent traversal failed, continue with just current PID
                pass

            if os.name == "nt":
                # Windows: Use PowerShell to list Python processes
                ps_cmd = [
                    "powershell", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | "
                    "Select-Object ProcessId, CommandLine | ConvertTo-Json"
                ]
                
                try:
                    raw = subprocess.check_output(
                        ps_cmd,
                        timeout=10,
                        shell=False,
                    ).decode("utf-8", errors="ignore")
                    
                    import json
                    procs = json.loads(raw)
                    
                    # Handle single result (not in array)
                    if isinstance(procs, dict):
                        procs = [procs]
                    
                    killed_count = 0
                    for p in procs:
                        pid = p.get("ProcessId")
                        cmdline = p.get("CommandLine", "")
                        
                        # Skip if no PID or protected
                        if not pid or pid in protected_pids:
                            continue
                        
                        # Kill if contains telegram_bot marker
                        if "telegram_bot" in cmdline.lower():
                            try:
                                proc = psutil.Process(pid)
                                proc.terminate()
                                killed_count += 1
                                logger.info(
                                    "[PollingManager] Killed duplicate process "
                                    "PID=%s",
                                    pid
                                )
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                    
                    if killed_count:
                        logger.info(
                            "[PollingManager] Cleaned %d duplicate process(es)",
                            killed_count
                        )
                    else:
                        logger.warning(
                            "[PollingManager] No duplicate processes found to kill"
                        )
                
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "[PollingManager] PowerShell process enumeration timed out"
                    )
                except Exception as exc:
                    logger.error(
                        "[PollingManager] Error parsing PowerShell output: %s",
                        exc
                    )
            
            else:
                # Unix-like systems: could use ps/grep, but not implemented here
                logger.warning(
                    "[PollingManager] Duplicate process cleanup not implemented "
                    "for this OS"
                )
        
        except Exception as exc:
            logger.error(
                "[PollingManager] Failed to clean duplicate processes: %s",
                exc,
                exc_info=True
            )
