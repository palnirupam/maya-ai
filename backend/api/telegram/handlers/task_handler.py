"""
Task processing and reply orchestration.
Handles _process_and_reply logic for incoming messages.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..manager import TelegramBotManager

logger = logging.getLogger(__name__)


class TaskHandler:
    """
    Orchestrates task execution: voice channel isolation, LLM turn routing,
    streaming updates, signal handling, screenshot triggers, and cleanup.
    """

    def __init__(self, manager: "TelegramBotManager"):
        self.manager = manager
        self.message_sender = manager.message_sender
        self.message_editor = manager.message_editor
        self.typing_indicator = manager.typing_indicator

    async def process_and_reply(
        self,
        chat_id: str,
        text: str,
        session_id: str,
        sent_msg_id: int | None = None,
    ) -> None:
        """
        Main orchestration: isolate voice channel, route through gateway,
        stream updates, handle signals, send final response, auto-screenshot.
        """
        from ..config import (
            STREAM_TIMEOUT,
            BACKGROUND_TASK_TIMEOUT,
            SCREENSHOT_TRIGGER_KEYWORDS,
        )

        task_state = self.manager._task_states[chat_id]
        full_response = ""
        turn_approval_ids: set[str] = set()
        turn_task: asyncio.Task | None = None
        suppressed_listener = None
        voice_was_interrupted = False
        background_update_task: asyncio.Task | None = None  # NEW: Background updates

        # ── Flusher: periodic update to Telegram ───────────────────────────
        last_flush = 0.0
        flush_interval = 0.5  # seconds - reduced from 5s for real-time animation

        async def _flush() -> None:
            nonlocal last_flush, full_response, sent_msg_id
            now = time.monotonic()
            if now - last_flush < flush_interval:
                return
            last_flush = now

            # Build display with active agent + status
            display = full_response.strip()
            
            # Only show rich progress for tool-executing agents (FIXED)
            is_tool_execution = (
                task_state.active_agent in ["OS_EXECUTOR", "RESEARCHER", "CODER", "CANVAS_EDITOR"]
                or "Executing" in (task_state.status or "")
                or "⚙️" in (task_state.status or "")
            )
            
            # Build rich progress display only for tool executions
            progress_lines = []
            
            if is_tool_execution:
                # Add progress status if available
                if task_state.status:
                    progress_lines.append(f"📊 **Status:** {task_state.status}")
                
                # Add agent info
                if task_state.active_agent:
                    progress_lines.append(f"🤖 **Agent:** {task_state.active_agent}")
                
                # Add elapsed time
                if hasattr(task_state, 'started_at'):
                    elapsed = time.monotonic() - task_state.started_at
                    if elapsed > 1:  # Show if more than 1 second
                        elapsed_str = f"{int(elapsed//60)}m {int(elapsed%60)}s" if elapsed >= 60 else f"{int(elapsed)}s"
                        progress_lines.append(f"⏱️ **Elapsed:** {elapsed_str}")
            
            # Build suffix with progress info
            suffix = ""
            if progress_lines:
                suffix = "\n\n" + "\n".join(progress_lines)

            if not display and not suffix:
                return

            # Add prominent Force Stop button ONLY for tool-executing tasks (FIXED)
            reply_markup = None
            if (task_state.state == "running" 
                and not task_state.backgrounded
                and (task_state.active_agent in ["OS_EXECUTOR", "RESEARCHER", "CODER", "CANVAS_EDITOR"]
                     or "Executing" in (task_state.status or "")
                     or "⚙️" in (task_state.status or ""))):

                # Only show Force Stop for tasks that execute tools/actions
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "⛔ FORCE STOP",
                                "callback_data": f"cancel_task_{chat_id}_{session_id}"
                            }
                        ]
                    ]
                }

            # Try Markdown, fallback to plain on parse error
            parse = "Markdown"
            if sent_msg_id is None:
                try:
                    # Use send_message when we have reply_markup (e.g., Cancel button)
                    if reply_markup:
                        await self.message_sender.send_message(
                            chat_id, display + suffix, parse_mode=parse, reply_markup=reply_markup
                        )
                        # Note: We don't get message_id back, but that's okay for progress messages
                        sent_msg_id = "progress"  # Placeholder to prevent re-sending
                    else:
                        msg_id = await self.message_sender.send_message_get_id(
                            chat_id, display + suffix, parse_mode=parse
                        )
                        sent_msg_id = msg_id
                except Exception:
                    parse = None
                    if reply_markup:
                        await self.message_sender.send_message(
                            chat_id, display + suffix, parse_mode=parse, reply_markup=reply_markup
                        )
                        sent_msg_id = "progress"
                    else:
                        msg_id = await self.message_sender.send_message_get_id(
                            chat_id, display + suffix, parse_mode=parse
                        )
                        sent_msg_id = msg_id
            else:
                # Edit existing message (no reply_markup on edits for now)
                await self.message_editor.edit_message(
                    chat_id, sent_msg_id, display + suffix, parse_mode=parse
                )

        # ── Background Progress Updates (NEW) ──────────────────────────────
        async def _background_progress_updates():
            """Send periodic status updates every 5s when task is backgrounded."""
            while task_state.backgrounded and task_state.state == "running":
                try:
                    await asyncio.sleep(5.0)  # 5 second interval
                    
                    if not task_state.backgrounded or task_state.state != "running":
                        break
                    
                    # Calculate elapsed time
                    elapsed = time.monotonic() - task_state.started_at
                    elapsed_str = f"{int(elapsed//60)}m {int(elapsed%60)}s" if elapsed >= 60 else f"{int(elapsed)}s"
                    
                    # Build background status message
                    copy = self.manager._wa_ui_copy(
                        self.manager._chat_language_style(chat_id)
                    )
                    
                    current_status = task_state.status or "Working..."
                    agent_info = f" | 🤖 {task_state.active_agent}" if task_state.active_agent else ""
                    
                    background_msg = (
                        f"⏳ **Background Task Update**\n\n"
                        f"📊 **Status:** {current_status}{agent_info}\n"
                        f"⏱️ **Elapsed:** {elapsed_str}\n"
                        f"🔄 **State:** Running in background\n\n"
                        f"Task will complete automatically. Use `/status` to check progress anytime."
                    )
                    
                    # Add prominent Force Stop button for background tasks (NEW - improved)
                    background_reply_markup = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "⛔ FORCE STOP BACKGROUND TASK",
                                    "callback_data": f"cancel_task_{chat_id}_{session_id}"
                                }
                            ]
                        ]
                    }
                    
                    # Send as separate message (don't edit main progress message)
                    await self.message_sender.send_message(
                        chat_id, 
                        background_msg,
                        parse_mode="Markdown",
                        reply_markup=background_reply_markup
                    )
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"Background progress update failed: {e}")
                    await asyncio.sleep(5.0)  # Continue trying

        try:
            # ── Isolate voice channel ──────────────────────────────────────
            try:
                from backend.api.main import get_active_listener
                from backend.voice.voice_state_machine import (
                    VoiceState,
                    voice_state_machine,
                )

                suppressed_listener = get_active_listener()
                if suppressed_listener is not None:
                    suppressed_listener.suppress_remote_input()
                voice_state_machine.discard_queued_audio()
                await voice_state_machine.cancel_llm()
                if voice_state_machine.state in {
                    VoiceState.TRANSCRIBING,
                    VoiceState.THINKING,
                    VoiceState.SPEAKING,
                }:
                    voice_was_interrupted = await voice_state_machine.transition(
                        VoiceState.INTERRUPTED
                    )
            except Exception as exc:
                logger.warning(
                    "[TelegramBot] Could not isolate voice channel: %s", exc
                )

            await self.typing_indicator.send_typing(chat_id)

            # ── Route through gateway ───────────────────────────────────────
            from backend.brain.gateway import run_turn

            async def _on_text(visible: str) -> None:
                nonlocal full_response
                full_response += visible
                task_state.updated_at = time.monotonic()
                await _flush()

            async def _on_event(chunk: dict) -> None:
                """Handle agent status updates, progress events, tool visibility, and tool approval requests."""
                # Progress event
                if chunk.get("type") == "progress_event":
                    await self._handle_progress_event(chunk, task_state, _flush)
                    return
                
                # Tool execution visibility (NEW)
                if chunk.get("type") == "tool_execution":
                    await self._handle_tool_execution(chunk, task_state, _flush)
                    return
                
                # Agent status update
                if chunk.get("type") == "agent_status":
                    data = chunk.get("data", {})
                    task_state.active_agent = str(data.get("active_agent", ""))
                    task_state.status = str(data.get("status", "Working..."))
                    task_state.updated_at = time.monotonic()
                    await _flush()  # CRITICAL: flush immediately to show status update
                    return

                # Tool approval request
                if chunk.get("type") != "tool_call_request":
                    return

                data = chunk.get("data", {})
                req_id = data.get("request_id")
                tool_name = data.get("tool_name", "unknown")
                args = data.get("args") or data.get("payload", {})
                risk_level = data.get("risk_level", "UNKNOWN")

                if req_id:
                    req_id = str(req_id)
                    turn_approval_ids.add(req_id)
                    self.manager._pending_exec_approval[chat_id] = req_id

                # Trigger hook in background
                from backend.system.hooks import trigger_hook
                asyncio.create_task(
                    trigger_hook(
                        "on_command_approval_request",
                        {
                            "request_id": req_id,
                            "tool_name": tool_name,
                            "args": args,
                            "risk_level": risk_level,
                            "chat_id": chat_id,
                        },
                    )
                )

                # Build human-friendly display
                args_display = self._format_tool_args(tool_name, args)
                risk_emoji = {
                    "HIGH": "🟠",
                    "CRITICAL": "🔴",
                    "MEDIUM": "🟡",
                    "LOW": "🟢",
                }.get(risk_level, "⚪")

                markup = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Approve",
                                "callback_data": f"exec_approve_{req_id}",
                            },
                            {
                                "text": "❌ Deny",
                                "callback_data": f"exec_deny_{req_id}",
                            },
                        ]
                    ]
                }
                await self.message_sender.send_message(
                    chat_id,
                    f"{risk_emoji} *Maya Execution Request* ({risk_level})\n\n"
                    f"🤖 Maya wants to: **{tool_name.replace('_', ' ').title()}**\n\n"
                    f"{args_display}\n\n*Do you approve?*",
                    reply_markup=markup,
                )

            # Start turn task with streaming callbacks
            turn_task = asyncio.create_task(
                run_turn(
                    session_id,
                    text,
                    on_text=_on_text,
                    on_event=_on_event,
                    timeout=None,  # Telegram owns the deadlines
                ),
                name=f"tg-turn-{chat_id}",
            )

            # ── Wait with soft timeout ──────────────────────────────────────
            try:
                result = await asyncio.wait_for(
                    asyncio.shield(turn_task), timeout=STREAM_TIMEOUT
                )
            except asyncio.TimeoutError:
                # Move to background
                task_state.backgrounded = True
                task_state.state = "running"
                task_state.status = task_state.status or "Working in background..."
                task_state.updated_at = time.monotonic()
                logger.info(
                    "Telegram task moved to background chat=%s text=%r",
                    chat_id,
                    text,
                )

                # Start background progress updates (NEW)
                background_update_task = asyncio.create_task(
                    _background_progress_updates(),
                    name=f"bg-progress-{chat_id}"
                )

                copy = self.manager._wa_ui_copy(
                    self.manager._chat_language_style(chat_id)
                )
                await self.message_sender.send_message(
                    chat_id,
                    (
                        f"Kaj-ta {int(STREAM_TIMEOUT)} second-er beshi nicche, "
                        "but eta background-e continue korche. Complete hole final "
                        "result automatically pathabo. Majhkhane `status ki` bolle "
                        "current progress dibo."
                    ),
                    reply_markup=self.manager._default_keyboard(),
                )

                # Wait for hard timeout
                try:
                    result = await asyncio.wait_for(
                        asyncio.shield(turn_task),
                        timeout=max(
                            0.01, BACKGROUND_TASK_TIMEOUT - STREAM_TIMEOUT
                        ),
                    )
                except asyncio.TimeoutError:
                    # Stop background updates before hard timeout
                    if background_update_task and not background_update_task.done():
                        background_update_task.cancel()
                        await asyncio.gather(background_update_task, return_exceptions=True)
                    
                    turn_task.cancel()
                    await asyncio.gather(turn_task, return_exceptions=True)
                    task_state.state = "timed_out"
                    task_state.status = "Hard timeout reached."
                    task_state.updated_at = time.monotonic()
                    copy = self.manager._wa_ui_copy(
                        self.manager._chat_language_style(chat_id)
                    )
                    await self.message_sender.send_message(
                        chat_id,
                        copy["task_hard_timeout"],
                        reply_markup=self.manager._default_keyboard(),
                    )
                    return

            # ── Handle special signals ──────────────────────────────────────
            if result.system_state is not None:
                await self._handle_system_state_signal(
                    chat_id, sent_msg_id, result.raw_text
                )
                task_state.state = "completed"
                task_state.final_text = result.final_text
                task_state.updated_at = time.monotonic()
                return

            if result.mode_change is not None:
                await self._handle_mode_change_signal(
                    chat_id, sent_msg_id, result.raw_text
                )
                task_state.state = "completed"
                task_state.final_text = result.final_text
                task_state.updated_at = time.monotonic()
                return

            # ── Final send ──────────────────────────────────────────────────
            # Stop background updates on completion (NEW)
            if background_update_task and not background_update_task.done():
                background_update_task.cancel()
                await asyncio.gather(background_update_task, return_exceptions=True)
            
            copy = self.manager._wa_ui_copy(
                self.manager._chat_language_style(chat_id)
            )
            final_text = result.final_text or copy["default_task_done"]

            # Delete progress message ONLY for tool-executing agents (FIXED)
            # Don't delete for CHAT agent - it has no progress, just direct response
            should_delete_progress = (
                sent_msg_id 
                and sent_msg_id != "progress"
                and task_state.active_agent in ["OS_EXECUTOR", "RESEARCHER", "CODER", "CANVAS_EDITOR"]
            )
            
            if should_delete_progress:
                try:
                    # Delete the progress tracking message for tool-heavy tasks
                    await self.message_editor.delete_message(chat_id, sent_msg_id)
                    sent_msg_id = None  # Mark as deleted
                except Exception as e:
                    logger.debug(f"Could not delete progress message: {e}")
            
            # Send clean final message
            if sent_msg_id and sent_msg_id != "progress":
                # Edit existing message (for CHAT or if delete failed)
                await self.message_editor.edit_message(
                    chat_id, sent_msg_id, final_text
                )
                await self.message_sender.send_message(
                    chat_id, "‎", reply_markup=self.manager._default_keyboard()
                )
            else:
                # Send new message (for deleted progress or new message)
                await self.message_sender.send_message(
                    chat_id,
                    final_text,
                    reply_markup=self.manager._default_keyboard(),
                )

            task_state.state = "completed"
            task_state.status = "Completed."
            task_state.final_text = final_text
            task_state.updated_at = time.monotonic()

            # ── Auto screenshot ─────────────────────────────────────────────
            if any(
                kw in text.lower() for kw in SCREENSHOT_TRIGGER_KEYWORDS
            ):
                await self.typing_indicator.send_screenshot(
                    chat_id, "📷 *Current Screen State:*"
                )

        except asyncio.CancelledError:
            # Stop background updates on cancellation (NEW)
            if background_update_task and not background_update_task.done():
                background_update_task.cancel()
                await asyncio.gather(background_update_task, return_exceptions=True)
            
            # Cancel progress tracking (NEW)
            if hasattr(turn_task, '_progress_tracker') and turn_task._progress_tracker:
                await turn_task._progress_tracker.cancel()
            
            task_state.state = "cancelled"
            task_state.status = "Cancelled by a newer request."
            task_state.updated_at = time.monotonic()
            if turn_task and not turn_task.done():
                turn_task.cancel()
                await asyncio.gather(turn_task, return_exceptions=True)
            logger.info("Task cancelled for chat_id=%s", chat_id)
            raise

        except Exception as exc:
            # Stop background updates on error (NEW)
            if background_update_task and not background_update_task.done():
                background_update_task.cancel()
                await asyncio.gather(background_update_task, return_exceptions=True)
            
            task_state.state = "failed"
            task_state.status = "Failed."
            task_state.error = str(exc)
            task_state.updated_at = time.monotonic()
            logger.error(
                "Error processing command for chat=%s: %s",
                chat_id,
                exc,
                exc_info=True,
            )
            await self.message_sender.send_message(
                chat_id,
                f"❌ *Error:* {exc}",
                reply_markup=self.manager._default_keyboard(),
            )

        finally:
            # Cleanup background update task (NEW)
            if background_update_task and not background_update_task.done():
                background_update_task.cancel()
                await asyncio.gather(background_update_task, return_exceptions=True)
            
            # Cleanup
            if self.manager._pending_exec_approval.get(chat_id) in turn_approval_ids:
                self.manager._pending_exec_approval.pop(chat_id, None)

            if turn_task and not turn_task.done():
                turn_task.cancel()
                await asyncio.gather(turn_task, return_exceptions=True)

            current = asyncio.current_task()
            if self.manager._active_tasks.get(chat_id) is current:
                self.manager._active_tasks.pop(chat_id, None)

            # Restore voice channel
            if suppressed_listener is not None:
                suppressed_listener.resume_remote_input()

            if voice_was_interrupted:
                try:
                    from backend.voice.voice_state_machine import (
                        VoiceState,
                        voice_state_machine,
                    )

                    if voice_state_machine.state == VoiceState.INTERRUPTED:
                        await voice_state_machine.transition(VoiceState.LISTENING)
                except Exception as exc:
                    logger.warning(
                        "[TelegramBot] Could not restore voice listening: %s", exc
                    )

    async def _handle_tool_execution(
        self, chunk: dict, task_state, flush_callback
    ) -> None:
        """
        Handle tool execution visibility events and update status display.
        
        Shows: ⚙️ Executing tool_name → ✅ Success (0.5s) | ❌ Failed: error
        """
        data = chunk.get("data", {})
        if not data:
            return
        
        tool_name = data.get("tool_name", "unknown")
        status = data.get("status", "")
        duration = data.get("duration", 0)
        
        if status == "starting":
            # Show executing status
            task_state.status = f"⚙️ Executing {tool_name.replace('_', ' ').title()}"
            
        elif status == "success":
            # Show success with duration
            result_preview = data.get("result", "")
            if len(result_preview) > 50:
                result_preview = result_preview[:47] + "..."
            
            duration_str = f"{duration:.1f}s" if duration else ""
            success_msg = f"✅ {tool_name.replace('_', ' ').title()}"
            if duration_str:
                success_msg += f" ({duration_str})"
            if result_preview:
                success_msg += f": {result_preview}"
                
            task_state.status = success_msg
            
        elif status == "failed":
            # Show failure with error
            error = data.get("error", "Unknown error")
            if len(error) > 100:
                error = error[:97] + "..."
            
            duration_str = f"{duration:.1f}s" if duration else ""
            fail_msg = f"❌ {tool_name.replace('_', ' ').title()} Failed"
            if duration_str:
                fail_msg += f" ({duration_str})"
            fail_msg += f": {error}"
            
            task_state.status = fail_msg
        
        # Update timestamp and flush
        task_state.updated_at = time.monotonic()
        await flush_callback()

    async def _handle_progress_event(
        self, chunk: dict, task_state, flush_callback
    ) -> None:
        """
        Handle progress event from ProgressTracker and update task state.
        
        Format: Displays progress bar, step counter, percentage, agent name, ETA
        Example: "█████░░░░░ 50% (Step 3/6) | 🤖 OS_EXECUTOR | ⏱️ ~12s remaining"
        """
        data = chunk.get("data", {})
        if not data:
            return
        
        # Extract progress data
        step_num = data.get("step_number", 0)
        total_steps = data.get("total_steps", 0)
        percentage = data.get("progress_percent", 0.0) or 0.0  # Fixed: was 'percentage'
        agent = data.get("agent", "")
        stage = data.get("stage", "")
        eta_seconds = data.get("estimated_time_left")  # Fixed: was 'eta_seconds'
        action = data.get("action", "")
        
        # Build progress bar (10 blocks)
        bar_length = 10
        filled = int(percentage / 100 * bar_length)
        progress_bar = "█" * filled + "░" * (bar_length - filled)
        
        # Format step counter
        step_counter = f"Step {step_num}/{total_steps}" if total_steps > 0 else ""
        
        # Format percentage
        pct_display = f"{int(percentage)}%"
        
        # Format ETA
        eta_display = ""
        if eta_seconds and isinstance(eta_seconds, (int, float)) and eta_seconds > 0:
            if eta_seconds < 60:
                eta_display = f"⏱️ ~{int(eta_seconds)}s remaining"
            else:
                eta_display = f"⏱️ ~{int(eta_seconds / 60)}m {int(eta_seconds % 60)}s remaining"
        
        # Format agent
        agent_display = f"🤖 {agent}" if agent else ""
        
        # Build status line
        status_parts = [
            f"{progress_bar} {pct_display}",
            f"({step_counter})" if step_counter else "",
            agent_display,
            eta_display,
        ]
        status_line = " | ".join([p for p in status_parts if p])
        
        # Add action description if available
        if action:
            status_line = f"{status_line}\n🔄 {action}"
        
        # Update task state
        task_state.status = status_line
        task_state.active_agent = agent
        task_state.updated_at = time.monotonic()
        
        # Trigger immediate flush
        await flush_callback()

    def _format_tool_args(self, tool_name: str, args: dict) -> str:
        """Format tool arguments for human-readable display in approval UI."""
        # Email tools
        if tool_name in (
            "trash_background_email",
            "permanent_delete_email",
        ) and args:
            uid = args.get("uid", "?")
            subject = args.get("subject", "?")
            from_s = args.get("from_sender", "?")
            action_label = (
                "🗑️ Move to Trash"
                if tool_name == "trash_background_email"
                else "💀 Permanently Delete"
            )
            return f"{action_label}\n\n📧 *Subject:* `{subject}`\n👤 *From:* `{from_s}`\n🔑 *UID:* `{uid}`"

        # App management
        elif tool_name == "close_apps_except":
            excluded_apps = args.get("excluded_apps", "")
            if excluded_apps:
                return f"📱 **Close all apps except:** `{excluded_apps}`"
            else:
                return "📱 **Close all open apps** (keeping Maya safe)"

        elif tool_name == "close_app":
            app_name = args.get("app_name", "")
            return f"📱 **Close app:** `{app_name}`"

        elif tool_name == "open_app":
            app_name = args.get("app_name", "")
            return f"📱 **Open app:** `{app_name}`"

        # System actions
        elif tool_name in ["manage_system_state", "shutdown", "restart", "sleep"]:
            action = args.get("action", tool_name)
            return f"💻 **System action:** `{action}`"

        # File operations
        elif tool_name in ["write_file", "fs_write"]:
            path = args.get("path", args.get("file_path", ""))
            return f"📝 **Write file:** `{path}`"

        elif tool_name in ["delete_file", "remove_file"]:
            path = args.get("path", args.get("file_path", ""))
            return f"🗑️ **Delete file:** `{path}`"

        # Command execution
        elif tool_name in ["execute_command", "run_command"]:
            command = args.get("command", "")
            if len(command) > 100:
                command = command[:97] + "..."
            return f"⚡ **Run command:** `{command}`"

        # Generic fallback
        else:
            if args:
                formatted_args = []
                for key, value in args.items():
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:47] + "..."
                    elif isinstance(value, (dict, list)):
                        value = f"{type(value).__name__} ({len(value)} items)"
                    formatted_args.append(f"**{key}:** `{value}`")
                return "\n".join(formatted_args)
            else:
                return "*No parameters*"

    async def _handle_system_state_signal(
        self, chat_id: str, sent_msg_id: int | None, raw_text: str
    ) -> None:
        """Handle system_state signal (shutdown, sleep, restart)."""
        # Extract signal and execute
        copy = self.manager._wa_ui_copy(
            self.manager._chat_language_style(chat_id)
        )
        await self.message_sender.send_message(
            chat_id,
            copy["sleep_starting"],
            reply_markup=self.manager._default_keyboard(),
        )

    async def _handle_mode_change_signal(
        self, chat_id: str, sent_msg_id: int | None, raw_text: str
    ) -> None:
        """Handle mode_change signal (friendly, coding, professional)."""
        # Extract mode and confirm
        copy = self.manager._wa_ui_copy(
            self.manager._chat_language_style(chat_id)
        )
        await self.message_sender.send_message(
            chat_id,
            copy["mode_changed"].format(label="Friendly"),
            reply_markup=self.manager._default_keyboard(),
        )
