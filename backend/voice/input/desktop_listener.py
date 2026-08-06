"""
Maya Desktop Microphone Listener
=================================
Captures audio from the system microphone, runs Silero VAD,
and feeds detected speech into the VoiceStateMachine's audio queue.

Init sequence (order matters):
  1. Open sounddevice InputStream (float32, 16kHz, mono)
  2. Calibrate ambient noise → set dynamic barge-in threshold
  3. Start VAD processing loop in locked mode

dtype contract:
  All audio data is float32, range [-1.0, 1.0].
  RMS is computed in float32 range [0.0, 1.0].
  BARGE_IN_SENSITIVITY multiplier applies to this float32 RMS range.
  Do NOT mix with int16 (range 0–32767) anywhere in this file.
"""

import asyncio
import logging
import os
import time
import tempfile
import wave
import struct

import numpy as np

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────────
SAMPLE_RATE       = 16000          # Hz — matches Whisper and Silero VAD
CHANNELS          = 1              # Mono
DTYPE             = "float32"      # Contract: all RMS ops use float32 [0.0, 1.0]
CHUNK_DURATION_MS = 32             # VAD chunk size — Silero VAD v4 requires >= 512 samples at 16kHz
CHUNK_SAMPLES     = 512            # Exactly 512 — minimum for Silero VAD (sr/chunk must be <= 31.25)
CALIBRATION_SECS  = 1.0            # Ambient noise measurement window
BARGE_IN_SENSITIVITY = 3.0        # Configurable — threshold = ambient_rms × this
MIN_BARGE_IN_THRESHOLD = 0.01     # Never let silent calibration produce threshold=0
DEFAULT_NATIVE_MIC_LOCKED = True  # Explicit UI/Telegram action is required

# Silence padding around detected speech (prevents clipping)
PRE_SPEECH_CHUNKS  = 5
POST_SPEECH_CHUNKS = 20            # ~600ms silence before cutting recording

# PID file for hot-reload protection
PID_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "voice_engine.pid")
PID_FILE = os.path.normpath(PID_FILE)


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_pid_file() -> bool:
    """
    PID file logic for hot-reload protection.
    Returns True if this process should init the voice engine.
    Returns False if another process is already running it.
    """
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                recorded_pid = int(f.read().strip())
            if _is_pid_alive(recorded_pid) and recorded_pid != os.getpid():
                logger.info(
                    f"[DesktopListener] Voice engine already running "
                    f"(PID {recorded_pid}). Skipping init."
                )
                return False
            else:
                logger.info(
                    f"[DesktopListener] Stale PID file found "
                    f"(PID {recorded_pid} not alive). Overwriting."
                )
        except (ValueError, IOError):
            pass  # Corrupt PID file — overwrite

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def _release_pid_file():
    """Delete the PID file during graceful shutdown."""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logger.info("[DesktopListener] PID file cleaned up.")
    except OSError as e:
        logger.warning(f"[DesktopListener] Failed to remove PID file: {e}")


class DesktopMicrophoneListener:
    """
    Native desktop microphone listener with VAD and ambient calibration.

    It starts locked by design. The frontend voice button uses its own bounded
    microphone session; native continuous listening requires an explicit
    Telegram ``/unlock``. This prevents room audio, speaker echo, or TV speech
    from becoming unsolicited Maya commands at backend startup.
    """

    def __init__(self, state_machine, barge_in: bool = False):
        self._sm = state_machine
        self._barge_in = barge_in
        self._running = False
        self._stream = None
        self._barge_in_threshold: float = 0.02  # safe default before calibration
        # Use the existing Maya SileroVAD wrapper (handles arbitrary chunk sizes)
        from backend.voice.vad.silero import vad as silero_vad
        self._vad = silero_vad
        self._audio_buffer: list[np.ndarray] = []
        # ── Sleep / Lock mode ────────────────────────────────────────────────────
        self._is_locked: bool = DEFAULT_NATIVE_MIC_LOCKED
        # Separate temporary remote suppression from the user's persistent lock.
        self._remote_suppression_count: int = 0

    @property
    def is_locked(self) -> bool:
        """True when microphone is in sleep/lock mode."""
        return self._is_locked or self._remote_suppression_count > 0

    @property
    def is_manually_locked(self) -> bool:
        """True only when the user explicitly locked the microphone."""
        return self._is_locked

    def lock(self) -> None:
        """Put microphone into sleep mode — no speech will be processed."""
        self._is_locked = True
        logger.info("[DesktopListener] 🔒 Microphone LOCKED (Sleep Mode ON).")

    def unlock(self) -> None:
        """Wake microphone from sleep mode — resume speech processing."""
        self._is_locked = False
        logger.info("[DesktopListener] 🔓 Microphone UNLOCKED (Sleep Mode OFF).")

    def suppress_remote_input(self) -> None:
        """Temporarily ignore speech while a remote command is running."""
        self._remote_suppression_count += 1
        logger.info(
            "[DesktopListener] Remote input suppression ON (count=%d).",
            self._remote_suppression_count,
        )

    def resume_remote_input(self) -> None:
        """Release one remote-command microphone suppression lease."""
        self._remote_suppression_count = max(0, self._remote_suppression_count - 1)
        logger.info(
            "[DesktopListener] Remote input suppression count=%d.",
            self._remote_suppression_count,
        )

    # ── Startup ─────────────────────────────────────────────────────────────────

    async def start(self):
        """Full init sequence respecting the ordering contract."""
        if not _acquire_pid_file():
            return  # Another process is already running

        try:
            import sounddevice as sd
        except ImportError:
            logger.error("[DesktopListener] sounddevice not installed. Run: pip install sounddevice")
            return

        # Step 1: Open mic stream (float32, 16kHz, mono)
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=CHUNK_SAMPLES,
            )
            self._stream.start()
            logger.info("[DesktopListener] Mic stream opened (float32, 16kHz, mono). VAD: SileroVAD (existing module).")
        except Exception as e:
            logger.error(f"[DesktopListener] Failed to open mic stream: {e}")
            _release_pid_file()
            return

        # Step 2: Calibrate ambient noise BEFORE starting VAD loop
        self._calibrate_ambient_noise()

        # Step 3: Start VAD processing loop. It drains audio without processing
        # while locked, until the user explicitly sends Telegram /unlock.
        self._running = True
        logger.info("[DesktopListener] Starting VAD loop (microphone locked by default).")
        asyncio.ensure_future(self._vad_loop())

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        _release_pid_file()
        logger.info("[DesktopListener] Stopped and PID file cleaned up.")

    # ── Ambient Calibration ──────────────────────────────────────────────────────

    def _calibrate_ambient_noise(self):
        """
        Record CALIBRATION_SECS of audio and compute float32 RMS.
        Sets barge-in threshold = ambient_rms × BARGE_IN_SENSITIVITY.
        Called AFTER stream.start(), BEFORE VAD loop.
        dtype: float32, range [0.0, 1.0]
        """
        try:
            n_chunks = int(CALIBRATION_SECS * 1000 / CHUNK_DURATION_MS)
            chunks = []
            for _ in range(n_chunks):
                data, _ = self._stream.read(CHUNK_SAMPLES)
                chunks.append(data[:, 0] if data.ndim > 1 else data)
            audio = np.concatenate(chunks)
            ambient_rms = float(np.sqrt(np.mean(audio ** 2)))
            self._barge_in_threshold = max(
                ambient_rms * BARGE_IN_SENSITIVITY,
                MIN_BARGE_IN_THRESHOLD,
            )
            logger.info(
                f"[DesktopListener] Calibration complete. "
                f"Ambient RMS={ambient_rms:.4f} "
                f"Threshold={self._barge_in_threshold:.4f} "
                f"(sensitivity×{BARGE_IN_SENSITIVITY})"
            )
        except Exception as e:
            logger.warning(
                f"[DesktopListener] Calibration failed ({e}). "
                f"Using default threshold {self._barge_in_threshold}."
            )

    # ── VAD Loop ─────────────────────────────────────────────────────────────────

    async def _vad_loop(self):
        """
        Continuous loop using accumulated-window VAD.

        WHY: get_speech_timestamps() needs ≥300ms audio to be reliable.
             Per-chunk (32ms) VAD never detects speech.
        HOW: Accumulate VAD_WINDOW_CHUNKS chunks (~480ms), run VAD on that
             window, then decide speech/silence for each chunk in the window.
        """
        from backend.voice.voice_state_machine import VoiceState

        VAD_WINDOW_CHUNKS = 15          # 15 × 32ms = ~480ms per VAD decision
        vad_accumulator: list[np.ndarray] = []   # chunks waiting for VAD

        speech_chunks: list[np.ndarray] = []
        silence_count = 0
        in_speech = False
        pre_buffer: list[np.ndarray] = []
        vad_start_ts = None

        while self._running:
            try:
                data, overflowed = await asyncio.to_thread(
                    self._stream.read, CHUNK_SAMPLES
                )
                if overflowed:
                    logger.debug("[DesktopListener] Buffer overflow — audio gap.")

                chunk = data[:, 0] if data.ndim > 1 else data  # 1D float32

                # ── Sleep / Lock mode — drain audio but do nothing ─────────────
                if self.is_locked:
                    vad_accumulator.clear()
                    pre_buffer.clear()
                    in_speech = False
                    silence_count = 0
                    speech_chunks = []
                    continue

                # ── Barge-in check ─────────────────────────────────────────────
                if self._barge_in and self._sm.state == VoiceState.SPEAKING:
                    rms = float(np.sqrt(np.mean(chunk ** 2)))
                    if rms > self._barge_in_threshold:
                        logger.info("[DesktopListener] Barge-in! Interrupting.")
                        await self._sm.transition(VoiceState.INTERRUPTED)
                        vad_accumulator.clear()
                        continue

                # ── Only process in LISTENING state ───────────────────────────
                if self._sm.state != VoiceState.LISTENING:
                    vad_accumulator.clear()
                    continue

                vad_accumulator.append(chunk)

                # ── Run VAD every VAD_WINDOW_CHUNKS chunks (~480ms) ────────────
                if len(vad_accumulator) < VAD_WINDOW_CHUNKS:
                    continue  # keep accumulating

                # We have a full window — run VAD on it
                window = np.concatenate(vad_accumulator)
                is_speech = self._vad.is_speech(window)
                window_chunks = list(vad_accumulator)
                vad_accumulator.clear()

                if is_speech:
                    if not in_speech:
                        in_speech = True
                        vad_start_ts = time.perf_counter()
                        speech_chunks = list(pre_buffer)  # include pre-roll
                        logger.debug("[DesktopListener] Speech started.")
                    speech_chunks.extend(window_chunks)
                    silence_count = 0

                else:  # silence window
                    if in_speech:
                        silence_count += VAD_WINDOW_CHUNKS
                        speech_chunks.extend(window_chunks)

                        if silence_count >= POST_SPEECH_CHUNKS:
                            # ── End of utterance ──────────────────────────────
                            vad_ms = (time.perf_counter() - vad_start_ts) * 1000
                            self._sm.record_vad(vad_ms)
                            logger.info(
                                f"[DesktopListener] Utterance captured "
                                f"({len(speech_chunks)} chunks, {vad_ms:.0f}ms VAD). "
                                f"Saving & enqueuing..."
                            )
                            audio_path = await asyncio.to_thread(
                                self._save_wav, speech_chunks
                            )
                            if audio_path:
                                await self._sm.enqueue_audio(audio_path)
                            in_speech = False
                            silence_count = 0
                            speech_chunks = []
                            pre_buffer.clear()
                    else:
                        # Silence — maintain rolling pre-speech buffer
                        pre_buffer.extend(window_chunks)
                        pre_buffer = pre_buffer[-PRE_SPEECH_CHUNKS:]

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DesktopListener] VAD loop error: {e}")
                await asyncio.sleep(0.1)

    # ── WAV Saver ────────────────────────────────────────────────────────────────

    def _save_wav(self, chunks: list[np.ndarray]) -> str | None:
        """Save float32 chunks as a 16-bit PCM WAV file for the transcriber."""
        try:
            audio = np.concatenate(chunks)
            # Convert float32 [-1.0, 1.0] → int16 [-32768, 32767]
            audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

            tmp = tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, prefix="maya_voice_"
            )
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_int16.tobytes())
            return tmp.name
        except Exception as e:
            logger.error(f"[DesktopListener] Failed to save WAV: {e}")
            return None


# ── Device auto-recovery wrapper ─────────────────────────────────────────────────

async def start_listener_with_recovery(state_machine, barge_in: bool = False):
    """
    Wraps DesktopMicrophoneListener with a 5-second auto-retry loop.
    Falls back to OS default device on driver crash or Bluetooth disconnect.
    """
    RETRY_DELAY = 5

    while True:
        listener = DesktopMicrophoneListener(state_machine, barge_in=barge_in)
        try:
            await listener.start()
            # Keep running until stop() is called externally
            while listener._running:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(
                f"[DesktopListener] Listener crashed: {e}. "
                f"Retrying in {RETRY_DELAY}s..."
            )
        finally:
            await listener.stop()

        await asyncio.sleep(RETRY_DELAY)
