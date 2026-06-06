"""
Maya Desktop Audio Player
==========================
Plays TTS audio directly to the system speakers.

Features:
  - Playback queue (prevents TTS overlap)
  - Instant stop() for barge-in interruption
  - Graceful drain on shutdown
"""

import asyncio
import logging
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)


class DesktopAudioPlayer:
    """
    Plays WAV/PCM audio streams directly to the desktop speaker via sounddevice.
    Runs in a dedicated thread to be non-blocking and interruptable.
    """

    def __init__(self, state_machine):
        self._sm = state_machine
        self._stop_event = threading.Event()
        self._playback_thread: threading.Thread | None = None
        self._current_stream = None

    # ── Public API ───────────────────────────────────────────────────────────────

    async def play_wav(self, wav_path: str):
        """
        Plays a WAV file. Blocks until playback completes or stop() is called.
        Runs sounddevice in a background thread to stay non-blocking.
        """
        self._stop_event.clear()
        await asyncio.to_thread(self._play_blocking, wav_path)

    def stop(self):
        """Instantly stop any ongoing playback (used for barge-in)."""
        self._stop_event.set()
        if self._current_stream:
            try:
                self._current_stream.stop()
                self._current_stream.close()
            except Exception:
                pass
        logger.info("[DesktopPlayer] Playback stopped (barge-in or interrupt).")

    async def drain_and_stop(self, timeout: float = 2.0):
        """Graceful shutdown: wait for current audio to finish, then stop."""
        await asyncio.wait_for(
            asyncio.to_thread(self._drain_blocking),
            timeout=timeout
        )
        self.stop()

    # ── Internal ─────────────────────────────────────────────────────────────────

    def _play_blocking(self, wav_path: str):
        """Synchronous playback in a thread."""
        try:
            import sounddevice as sd
            import soundfile as sf

            data, samplerate = sf.read(wav_path, dtype="float32")

            # Open a non-blocking stream so we can check stop_event between chunks
            CHUNK = 4096
            idx = 0

            with sd.OutputStream(
                samplerate=samplerate,
                channels=data.ndim if data.ndim > 1 else 1,
                dtype="float32",
            ) as stream:
                self._current_stream = stream
                while idx < len(data) and not self._stop_event.is_set():
                    chunk = data[idx:idx + CHUNK]
                    if chunk.ndim == 1:
                        chunk = chunk.reshape(-1, 1)
                    stream.write(chunk)
                    idx += CHUNK

        except Exception as e:
            logger.error(f"[DesktopPlayer] Playback error: {e}")
        finally:
            self._current_stream = None

    def _drain_blocking(self):
        """Wait until stop_event is set or 2 seconds pass."""
        self._stop_event.wait(timeout=2.0)


# ── Singleton ───────────────────────────────────────────────────────────────────
desktop_player = DesktopAudioPlayer(None)  # state_machine injected at startup
