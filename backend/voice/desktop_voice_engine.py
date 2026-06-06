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

                # ── Step 3: Send to Maya Brain (Orchestrator) ─────────────────
                await state_machine.transition(VoiceState.THINKING)

                # Create cancellation token for this LLM request
                self._current_llm_cancel = state_machine.get_llm_cancel_event()

                llm_start = time.perf_counter()
                full_response = ""
                sentence_buffer = ""
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
                            async for chunk in tts_router.stream_audio(sentence, language=None, emotion=emotion):
                                audio_bytes += chunk
                            tts_ms = (time.perf_counter() - tts_start) * 1000
                            state_machine.record_tts(tts_ms)

                            if audio_bytes and state_machine.state != VoiceState.INTERRUPTED:
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
                async for chunk in orchestrator.process_user_input_stream(
                    DESKTOP_SESSION_ID, text, None
                ):
                    # Check if user interrupted during THINKING
                    if state_machine.state == VoiceState.INTERRUPTED:
                        logger.info("[DesktopVoiceEngine] Interrupted during LLM — stopping.")
                        break

                    # Check cancellation token
                    if self._current_llm_cancel and self._current_llm_cancel.is_set():
                        logger.info("[DesktopVoiceEngine] LLM cancelled by new request.")
                        break

                    if isinstance(chunk, dict):
                        continue  # Skip tool call events for now

                    sentence_buffer += chunk
                    full_response += chunk

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

                llm_ms = (time.perf_counter() - llm_start) * 1000
                state_machine.record_llm(llm_ms)

                # Flush any remaining text in buffer
                if sentence_buffer.strip() and state_machine.state != VoiceState.INTERRUPTED:
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
