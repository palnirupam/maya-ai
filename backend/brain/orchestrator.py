import asyncio
import logging
from typing import Dict
from .providers.base import LLMProvider
from .providers.gemini_adapter import GeminiAdapter

logger = logging.getLogger(__name__)

class ConversationOrchestrator:
    """
    Manages conversation memory, session context, and routes queries 
    to the appropriate LLM provider.
    """
    def __init__(self):
        self.provider: LLMProvider = GeminiAdapter()
        self.sessions: Dict[str, list[dict]] = {}
        self._dirty_sessions: set[str] = set()

    def _persist_session_memory(self, session_id: str, role: str, content: str) -> None:
        """Persist conversational turns for Dreaming Mode compaction.

        The in-memory session window is only a short working context. Dreaming
        Mode reads from the SessionMemory table, so user/assistant turns must be
        copied there as they happen.
        """
        if role not in {"user", "assistant"}:
            return
        if not content or not str(content).strip():
            return

        from datetime import datetime, timezone
        from ..database.connection import SessionLocal
        from ..database.models import SessionMemory
        from .memory.session_security import encrypt_session_content

        db = SessionLocal()
        try:
            db.add(SessionMemory(
                session_id=session_id,
                role=role,
                content=encrypt_session_content(str(content)),
                timestamp=datetime.now(timezone.utc),
            ))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(f"[Orchestrator] Failed to persist SessionMemory: {exc}")
        finally:
            db.close()

    def mark_sessions_dirty(self) -> None:
        """Mark all active session IDs dirty so their system prompts refresh on next turn."""
        for sid in list(self.sessions.keys()):
            self._dirty_sessions.add(sid)

    def get_session(self, session_id: str, initial_context: str = "") -> list[dict]:
        if session_id in self._dirty_sessions and session_id in self.sessions:
            from .personality.maya_personality import prompt_builder
            system_prompt = prompt_builder.get_system_prompt()
            if self.sessions[session_id] and self.sessions[session_id][0].get("role") == "system":
                self.sessions[session_id][0]["content"] = system_prompt
            self._dirty_sessions.discard(session_id)

        if session_id not in self.sessions:
            from .personality.maya_personality import prompt_builder
            from .memory.long_term_memory import build_memory_context_block

            system_prompt = prompt_builder.get_system_prompt()
            memory_block = build_memory_context_block(
                active_category=None,
                context_text=initial_context
            )

            if memory_block:
                system_prompt += "\n" + memory_block

            try:
                from backend.skills.md_loader import get_skills_prompt_block
                skills_block = get_skills_prompt_block()
                if skills_block:
                    system_prompt += "\n" + skills_block
                    logger.debug(f"[Orchestrator] Injected skills block into session '{session_id}'")
            except Exception as exc:
                logger.warning(f"[Orchestrator] Skills injection skipped: {exc}")

            self.sessions[session_id] = [
                {"role": "system", "content": system_prompt}
            ]
        return self.sessions[session_id]

    def add_to_memory(self, session_id: str, role: str, content: str, reasoning_content: str = None):
        session = self.get_session(session_id, initial_context=content if role == "user" else "")
        msg = {"role": role, "content": content}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        session.append(msg)

        self._persist_session_memory(session_id, role, content)

    async def _prepare_session_context(self, session_id: str) -> list[dict]:
        """Compact a session when needed and return its active context."""
        from .memory.context_condenser import get_condenser

        context = self.get_session(session_id)
        condenser = get_condenser(session_id)
        if condenser.needs_condensing(context):
            context = await condenser.condense(context)
            self.sessions[session_id] = context
            logger.info("[Orchestrator] Context condensed for session %s", session_id)
        return context

    def release_session(self, session_id: str) -> bool:
        """Release ephemeral in-memory state without deleting persisted memory."""
        removed = self.sessions.pop(session_id, None) is not None

        from .agents.agent_team import evict_session_state
        from .budget_manager import budget_manager
        from .memory.context_condenser import evict_condenser

        evict_condenser(session_id)
        budget_manager.reset_session(session_id)
        evict_session_state(session_id)
        if removed:
            logger.info("[Orchestrator] Released ephemeral session %s", session_id)
        return removed

    async def process_user_input(self, session_id: str, text: str, image_base64: str = None) -> str:
        """Process a full text input from the user and get a response."""
        logger.info(f"Processing input for session {session_id}: {text}")
        
        import time
        from datetime import datetime, timezone
        from backend.system.canvas import active_session_id
        from backend.system.observability import observability, RequestMetrics
        
        token = active_session_id.set(session_id)
        start_time = time.monotonic()
        try:
            self.add_to_memory(session_id, "user", text)
            context = await self._prepare_session_context(session_id)

            response_text = await self.provider.generate_response(context, text, image_base64)
            self.add_to_memory(session_id, "assistant", response_text)

            latency = int((time.monotonic() - start_time) * 1000)
            await observability.log(RequestMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                session_id=session_id,
                intent_class="standard",
                tokens_input=len(text) // 4,
                tokens_output=len(response_text) // 4,
                latency_ms=latency,
                model_used=getattr(self.provider, 'model_name', 'provider_default'),
                model_version=getattr(self.provider, 'model_name', 'provider_default'),
                model_tier='fast',
                tool_calls=[],
                verifier_retries=0,
                fast_path_hit=False,
                error=None
            ))

            return response_text
        except Exception as e:
            latency = int((time.monotonic() - start_time) * 1000)
            await observability.log(RequestMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                session_id=session_id,
                intent_class="standard",
                tokens_input=len(text) // 4,
                tokens_output=0,
                latency_ms=latency,
                model_used="unknown",
                model_version="unknown",
                model_tier='fast',
                tool_calls=[],
                verifier_retries=0,
                fast_path_hit=False,
                error=str(e)
            ))
            raise
        finally:
            try:
                active_session_id.reset(token)
            except ValueError as e:
                # Handle context token error when task is cancelled or context changed
                logger.debug(f"[Orchestrator] Context token reset failed (task cancelled): {e}")
                pass

    async def process_user_input_stream(self, session_id: str, text: str, image_base64: str = None):
        """Process input and stream the response back in chunks, delegating to the Multi-Agent team workflow."""
        logger.info(f"Streaming input for session {session_id} using multi-agent workflow: {text}")
        
        import time
        from datetime import datetime, timezone
        from backend.system.canvas import active_session_id
        from backend.system.observability import observability, RequestMetrics
        
        token = active_session_id.set(session_id)
        start_time = time.monotonic()
        output_char_count = 0  # count chars, not hold chunks in memory
        assistant_chunks: list[str] = []
        persisted = False
        try:
            self.add_to_memory(session_id, "user", text)
            context_history = await self._prepare_session_context(session_id)

            from .agents import agent_team
            from .progress_tracker import ProgressTracker

            # Store all events for later emission (SIMPLIFIED - sync callbacks)
            events_queue = []
            
            def _queue_progress_event(event):
                """Queue progress event for emission (sync callback)."""
                events_queue.append({
                    "type": "progress_event",
                    "data": {
                        "step_number": event.step_number,
                        "total_steps": event.total_steps,
                        "progress_percent": event.progress_percent,  # FIXED: was 'percentage'
                        "agent": event.agent,
                        "stage": event.stage.value if event.stage else "",
                        "elapsed_time": event.elapsed_time,  # FIXED: was 'eta_seconds'
                        "action": event.action,
                        "metadata": event.metadata,
                    }
                })
                return None  # Sync function, no coroutine
            
            def _queue_tool_event(event_data):
                """Queue tool execution event for emission (sync callback)."""
                events_queue.append(event_data)
                return None  # Sync function, no coroutine
            
            progress_tracker = ProgressTracker()
            progress_tracker.add_callback(_queue_progress_event)

            try:
                async for chunk in agent_team.execute_workflow(
                    session_id=session_id,
                    text=text,
                    context_history=context_history,
                    image_base64=image_base64,
                    progress_tracker=progress_tracker,
                    tool_event_callback=_queue_tool_event
                ):
                    # Store progress_tracker reference for cancellation (NEW)
                    current_task = asyncio.current_task()
                    if current_task:
                        current_task._progress_tracker = progress_tracker
                    
                    # Emit any queued events first
                    while events_queue:
                        yield events_queue.pop(0)
                    
                    # chunks can be str (text) or dict (events). Only count str chars.
                    if isinstance(chunk, str):
                        output_char_count += len(chunk)
                        assistant_chunks.append(chunk)
                    yield chunk
            except GeneratorExit:
                # Handle generator cancellation gracefully
                logger.debug(f"[Orchestrator] Stream generator cancelled for session {session_id}")
                raise

            assistant_text = "".join(assistant_chunks).strip()
            if assistant_text:
                self._persist_session_memory(session_id, "assistant", assistant_text)
                persisted = True

            latency = int((time.monotonic() - start_time) * 1000)
            from .budget_manager import budget_manager
            downgrade = budget_manager.record_usage(
                session_id, len(text) // 4, output_char_count // 4
            )
            active_tier = budget_manager.get_active_tier(session_id)
            if downgrade:
                old_tier, new_tier = downgrade
                await observability.log(RequestMetrics(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    session_id=session_id,
                    intent_class="budget_downgrade",
                    tokens_input=0,
                    tokens_output=0,
                    latency_ms=0,
                    model_used=old_tier,
                    model_version=new_tier,
                    model_tier=new_tier,
                    tool_calls=[],
                    verifier_retries=0,
                    fast_path_hit=False,
                    error=f"downgraded {old_tier}->{new_tier}"
                ))
            await observability.log(RequestMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                session_id=session_id,
                intent_class="workflow",
                tokens_input=len(text) // 4,
                tokens_output=output_char_count // 4,
                latency_ms=latency,
                model_used=getattr(self.provider, 'model_name', 'agent_team'),
                model_version=getattr(self.provider, 'model_name', 'agent_team'),
                model_tier=active_tier,
                tool_calls=[],
                verifier_retries=0,
                fast_path_hit=False,
                error=None
            ))
        except BaseException as e:
            if not persisted and assistant_chunks:
                partial_text = "".join(assistant_chunks).strip()
                if partial_text:
                    try:
                        self._persist_session_memory(session_id, "assistant", partial_text)
                        persisted = True
                    except Exception as persist_err:
                        logger.warning(f"[Orchestrator] Could not persist partial stream on cancel: {persist_err}")
            latency = int((time.monotonic() - start_time) * 1000)
            try:
                await observability.log(RequestMetrics(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    session_id=session_id,
                    intent_class="workflow",
                    tokens_input=len(text) // 4,
                    tokens_output=output_char_count // 4,
                    latency_ms=latency,
                    model_used="unknown",
                    model_version="unknown",
                    model_tier='fast',
                    tool_calls=[],
                    verifier_retries=0,
                    fast_path_hit=False,
                    error=str(e) or e.__class__.__name__
                ))
            except Exception:
                pass
            raise
        finally:
            try:
                active_session_id.reset(token)
            except ValueError as e:
                # Handle context token error when task is cancelled or context changed
                logger.debug(f"[Orchestrator] Context token reset failed (task cancelled): {e}")
                pass

orchestrator = ConversationOrchestrator()
