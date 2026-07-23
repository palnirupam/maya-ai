"""
Maya Desktop Voice Engine
==========================
Connects the DesktopMicrophoneListener → Transcriber → Orchestrator → TTS → Speaker.

This is the main loop that makes Maya work completely without a browser:
  Mic → VAD → Whisper/Gemini STT → Maya Brain → TTS → Desktop Speaker
"""

import asyncio
import logging
import io
import re
import time
import tempfile
import os

logger = logging.getLogger(__name__)

# Desktop session ID (fixed — desktop is a single persistent session)
DESKTOP_SESSION_ID = "desktop_native_session"

# Internal control tokens the brain embeds in the text stream. They are signals
# for the channel handler, never words for the user — the voice engine must not
# speak them aloud (the WebSocket handler already suppresses them before TTS).
_CONTROL_TOKENS = ("SYSTEM_STATE_TRIGGERED:", "MODE_CHANGE_TRIGGERED:")


def _is_control_token_stream(accumulated_text: str) -> bool:
    """True when the accumulated response is really a control token, not speech.

    Matches only when a token leads the response (after whitespace) so a normal
    reply that merely quotes the phrase later is never silenced.
    """
    return accumulated_text.lstrip().startswith(_CONTROL_TOKENS)


async def _forward_desktop_gateway_event(event: dict) -> None:
    """Bridge native voice approval requests to the desktop WebSocket UI."""
    if not isinstance(event, dict) or event.get("type") != "tool_call_request":
        return

    data = event.get("data")
    if not isinstance(data, dict):
        logger.warning("[DesktopVoiceEngine] Ignoring malformed tool approval event.")
        return

    from backend.api.websocket.manager import manager

    if manager.active_connections:
        await manager.broadcast_event("tool_approval_request", data)
        logger.info(
            "[DesktopVoiceEngine] Forwarded approval request %s to %d UI client(s).",
            data.get("request_id", "unknown"),
            len(manager.active_connections),
        )
        return

    # Native voice has no approve/deny interaction of its own. Fail closed when
    # the UI is unavailable instead of leaving the agent blocked for five minutes.
    request_id = data.get("request_id")
    if not request_id:
        logger.warning("[DesktopVoiceEngine] Approval event has no request_id.")
        return

    from backend.brain.reasoning.tool_planner import tool_planner

    result = tool_planner.resolve_tool(
        request_id,
        approved=False,
        user_id="desktop_voice_no_ui",
    )
    logger.warning(
        "[DesktopVoiceEngine] No UI connected; denied approval request %s (%s).",
        request_id,
        result.get("status", "unknown") if isinstance(result, dict) else "unknown",
    )


class DesktopVoiceEngine:
    """
    Orchestrates the full native desktop voice pipeline:
      1. Listens for audio files from the DesktopMicrophoneListener queue
      2. Transcribes audio via Whisper / Gemini STT
      3. Sends transcribed text to the Maya Orchestrator (LLM brain)
      4. Streams LLM response → TTS → plays audio natively to speakers
    """

    def __init__(self):
        self._running = False
        self._current_llm_cancel: asyncio.Event | None = None

    async def start(self, state_machine, listener):
        """Main processing loop — runs as a background asyncio task."""
        self._running = True
        logger.info("[DesktopVoiceEngine] Pipeline started. Waiting for speech...")

        from backend.voice.voice_state_machine import VoiceState
        from backend.voice.input.transcriber import transcriber
        from backend.brain.orchestrator import orchestrator
        from backend.brain.language_style import (
            detect_conversation_style,
            set_latest_conversation_style,
            tts_language_for_style,
        )
        from backend.voice.output.tts_router import tts_router
        from backend.voice.emotions.formatter import formatter as emotion_formatter
        from backend.voice.output.desktop_player import desktop_player

        while self._running:
            try:
                # ── Step 1: Wait for speech audio from the VAD queue ───────────
                audio_path = await state_machine.dequeue_audio()

                if not audio_path or not os.path.exists(audio_path):
                    continue

                await state_machine.transition(VoiceState.TRANSCRIBING)
                logger.info(f"[DesktopVoiceEngine] Transcribing: {audio_path}")

                # ── Step 2: Transcribe (Gemini STT → Whisper fallback) ─────────
                stt_start = time.perf_counter()
                text = await transcriber.transcribe(audio_path)
                stt_ms = (time.perf_counter() - stt_start) * 1000
                state_machine.record_stt(stt_ms)

                if not text or not text.strip():
                    logger.info("[DesktopVoiceEngine] Empty transcription — ignoring.")
                    await state_machine.transition(VoiceState.LISTENING)
                    continue

                logger.info(f"[DesktopVoiceEngine] You said: {text}")
                turn_style = detect_conversation_style(
                    text,
                    orchestrator.sessions.get(DESKTOP_SESSION_ID, []),
                )
                set_latest_conversation_style(turn_style)
                turn_language = tts_language_for_style(turn_style)

                # ── Step 3: Send to Maya Brain (Orchestrator) ─────────────────
                await state_machine.transition(VoiceState.THINKING)

                # Create cancellation token for this LLM request
                self._current_llm_cancel = state_machine.get_llm_cancel_event()

                llm_start = time.perf_counter()
                full_response = ""
                sentence_buffer = ""
                # A turn whose text stream is really a control token
                # (SYSTEM_STATE_TRIGGERED:/MODE_CHANGE_TRIGGERED:) must never be
                # spoken aloud — the token is an internal signal, not an answer.
                is_control_token_turn = False
                tts_queue = asyncio.Queue()

                # TTS worker — plays audio sentences sequentially
                async def tts_worker():
                    while True:
                        item = await tts_queue.get()
                        if item is None:
                            tts_queue.task_done()
                            break
                        sentence, emotion = item
                        try:
                            # Check for barge-in / interruption before playing
                            if state_machine.state == VoiceState.INTERRUPTED:
                                tts_queue.task_done()
                                break

                            # Collect all TTS audio chunks
                            audio_bytes = b""
                            tts_start = time.perf_counter()
                            async for chunk in tts_router.stream_audio(
                                sentence,
                                language=turn_language,
                                emotion=emotion,
                            ):
                                audio_bytes += chunk
                            tts_ms = (time.perf_counter() - tts_start) * 1000
                            state_machine.record_tts(tts_ms)

                            if audio_bytes and state_machine.state != VoiceState.INTERRUPTED:
                                # Only transition to SPEAKING if not already there
                                # (multiple sentences in same response re-use same SPEAKING state)
                                if state_machine.state != VoiceState.SPEAKING:
                                    await state_machine.transition(VoiceState.SPEAKING)
                                # Write to temp wav file and play natively
                                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix="maya_tts_") as f:
                                    f.write(audio_bytes)
                                    tts_path = f.name
                                try:
                                    await desktop_player.play_wav(tts_path)
                                finally:
                                    try:
                                        os.remove(tts_path)
                                    except Exception:
                                        pass

                        except Exception as e:
                            logger.error(f"[DesktopVoiceEngine] TTS error: {e}")
                        finally:
                            tts_queue.task_done()

                worker_task = asyncio.create_task(tts_worker())

                # Stream LLM response and split into sentences for low-latency TTS
                def _should_stop():
                    # Barge-in during THINKING, or a newer request cancelled this one.
                    if state_machine.state == VoiceState.INTERRUPTED:
                        logger.info("[DesktopVoiceEngine] Interrupted during LLM — stopping.")
                        return True
                    if self._current_llm_cancel and self._current_llm_cancel.is_set():
                        logger.info("[DesktopVoiceEngine] LLM cancelled by new request.")
                        return True
                    return False

                async def _on_text(visible):
                    nonlocal sentence_buffer, full_response, is_control_token_turn
                    sentence_buffer += visible
                    full_response += visible

                    # Control-token turns carry an internal signal, not speech.
                    # The WebSocket handler suppresses these before TTS; the voice
                    # engine must do the same or Maya literally says
                    # "SYSTEM_STATE_TRIGGERED:shutdown" out loud.
                    if is_control_token_turn:
                        return
                    if _is_control_token_stream(full_response):
                        is_control_token_turn = True
                        sentence_buffer = ""
                        return

                    # Find sentence boundaries and send to TTS queue
                    match = re.search(r'(?<!\d)[.!?।\u0964]+', sentence_buffer)
                    if not match and len(sentence_buffer) > 200:
                        match = re.search(r'(?<!\d)[,;]+', sentence_buffer)

                    if match:
                        sentence = sentence_buffer[:match.end()].strip()
                        sentence_buffer = sentence_buffer[match.end():]
                        if sentence:
                            # Strip macro blocks from speech
                            sentence = re.sub(r'```macro.*?(?:```|$)', '', sentence, flags=re.DOTALL).strip()
                            if sentence:
                                emotion = emotion_formatter.extract_emotion(sentence) or "neutral"
                                tts_queue.put_nowait((sentence, emotion))

                # Route the turn through the shared channel gateway: it CoT-strips
                # the text and polls should_stop for barge-in / cancel. on_text does
                # sentence splitting for low-latency TTS; timeout=None keeps the
                # real-time stream unbounded. Approval events are bridged to the
                # desktop UI and fail closed when no UI is connected.
                from backend.brain.gateway import run_turn
                await run_turn(
                    DESKTOP_SESSION_ID, text,
                    on_text=_on_text,
                    on_event=_forward_desktop_gateway_event,
                    should_stop=_should_stop,
                    timeout=None,
                )

                llm_ms = (time.perf_counter() - llm_start) * 1000
                state_machine.record_llm(llm_ms)

                # Flush any remaining text in buffer (never for a control-token turn)
                if (
                    not is_control_token_turn
                    and sentence_buffer.strip()
                    and state_machine.state != VoiceState.INTERRUPTED
                ):
                    remaining = sentence_buffer.strip()
                    remaining = re.sub(r'```macro.*?(?:```|$)', '', remaining, flags=re.DOTALL).strip()
                    if remaining:
                        emotion = emotion_formatter.extract_emotion(remaining) or "neutral"
                        tts_queue.put_nowait((remaining, emotion))

                # Signal TTS worker to stop
                tts_queue.put_nowait(None)
                await worker_task

                state_machine.finalize_metric()
                logger.info(f"[DesktopVoiceEngine] Response complete: {full_response[:80]}...")

                # ── Return to LISTENING ─────────────────────────────────────────
                if state_machine.state not in (VoiceState.INTERRUPTED,):
                    await state_machine.transition(VoiceState.LISTENING)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DesktopVoiceEngine] Pipeline error: {e}", exc_info=True)
                try:
                    from backend.voice.voice_state_machine import VoiceState
                    await state_machine.transition(VoiceState.LISTENING)
                except Exception:
                    pass
                await asyncio.sleep(0.5)

    def stop(self):
        self._running = False


# ── Singleton ───────────────────────────────────────────────────────────────────
desktop_voice_engine = DesktopVoiceEngine()
