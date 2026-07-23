import logging
import numpy as np
import subprocess
import os
import base64
from typing import Optional
from faster_whisper import WhisperModel

from ...brain.language_style import latinize_transcript

logger = logging.getLogger(__name__)

# ── Hallucination guard ─────────────────────────────────────────────────────
# Both Whisper and Gemini STT invent short stock phrases when handed silence or
# ambient noise (fan, keyboard, distant chatter). The amplitude gate below only
# catches near-silent clips; anything with mild background noise sails through
# and comes back as one of these. Without this filter that garbage is treated
# as a real user turn and Maya replies unprompted.
import re as _re

_HALLUCINATION_PHRASES = {
    "you", "thank you", "thank you.", "thanks", "thanks for watching",
    "thanks for watching!", "thank you for watching", "please subscribe",
    "subscribe", "bye", "bye.", "okay", "ok", ".", "..", "...", "।", "।।",
    "so", "uh", "um", "hmm", "hm", "yeah", "the", "a", "i", "oh",
    "silence", "[silence]", "[music]", "[music playing]", "music",
    "dhonnobad", "thik ache", "accha",
}


def _is_probable_hallucination(text: str) -> bool:
    """Return True if a transcript is almost certainly STT noise, not speech."""
    if not text:
        return True
    stripped = text.strip()
    # Strip surrounding punctuation/whitespace for the phrase comparison.
    normalized = _re.sub(r"[\s\.\!\?,।।]+", " ", stripped).strip().lower()
    if not normalized:
        return True
    if normalized in _HALLUCINATION_PHRASES:
        return True
    # A meaningful command has real letters; a clip of just punctuation/symbols
    # (".", "...", "♪") carries no intent.
    if not _re.search(r"[a-z0-9ঀ-৿ऀ-ॿ]", normalized):
        return True
    return False

# ── Gemini STT ────────────────────────────────────────────────────────────────
# Uses Gemini's audio understanding capability to transcribe Bengali/Hindi/English
# and mixed-language (Banglish/Hindilish) with near-perfect accuracy.
# Falls back to Faster-Whisper if Gemini API is unavailable.

def _get_gemini_stt_url() -> str:
    try:
        from ...config.model_config import get_model
        model_name = get_model("fast")
    except ImportError:
        model_name = "gemini-3.5-flash"  # safe default if run standalone
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )

_STT_PROMPT = (
    "Transcribe the following audio exactly as spoken. "
    "The speaker may use Bengali, Hindi, English, or any mix of these languages "
    "(Banglish / Hindilish). Write every word with English/Latin letters: romanize "
    "spoken Bangla as natural Banglish and spoken Hindi as natural Hindilish, while "
    "keeping English words unchanged. Never output Bengali or Devanagari characters. "
    "Output ONLY the transcription - no explanations, no punctuation corrections, "
    "and no extra words."
)


def _get_gemini_api_key() -> Optional[str]:
    """Fetch Gemini API key — tries DB first, then environment variable."""
    key = None
    # Try both import path styles (standalone script vs uvicorn module)
    for module_prefix in ("backend.database", "database"):
        try:
            conn_mod = __import__(f"{module_prefix}.connection", fromlist=["SessionLocal"])
            model_mod = __import__(f"{module_prefix}.models", fromlist=["UserPreferences"])
            crypto_mod = __import__(f"{module_prefix}.crypto", fromlist=["crypto_manager"])
            db = conn_mod.SessionLocal()
            try:
                pref = db.query(model_mod.UserPreferences).filter(
                    model_mod.UserPreferences.key == "GEMINI_API_KEY"
                ).first()
                if pref and pref.value:
                    key = crypto_mod.crypto_manager.decrypt(pref.value).strip()
                    break
            finally:
                db.close()
        except Exception:
            continue
    if not key:
        # Last resort: environment variable
        key = os.getenv("GEMINI_API_KEY")

    if key:
        key_lower = key.lower()
        if any(key_lower.startswith(prefix) for prefix in ("gsk_", "sk-", "nvapi-", "sk-or-")):
            logger.debug(f"[GeminiSTT] API Key appears to be for another provider ({key[:4]}...) — bypassing Gemini STT.")
            return None
    return key


async def _transcribe_with_gemini(wav_path: str) -> Optional[str]:
    """
    Transcribe a WAV file using Gemini's audio understanding API.
    Returns transcribed text, or None if the call fails (triggers Whisper fallback).
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        return None

    try:
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        # Gemini has a 20MB inline data limit — skip and use Whisper for large files
        if len(audio_bytes) > 18 * 1024 * 1024:
            logger.warning("[GeminiSTT] Audio file too large (>18MB) — using Whisper.")
            return None

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        payload = {
            "contents": [{
                "parts": [
                    {"text": _STT_PROMPT},
                    {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
                ]
            }],
            "generationConfig": {"temperature": 0},
        }

        import httpx
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                _get_gemini_stt_url(),
                params={"key": api_key},
                json=payload,
            )

        if resp.status_code != 200:
            logger.warning(f"[GeminiSTT] API error {resp.status_code} — using Whisper.")
            return None

        data = resp.json()
        text = latinize_transcript(
            data["candidates"][0]["content"]["parts"][0]["text"]
        )
        logger.info(f"[GeminiSTT] ✅ Transcribed: {text}")
        return text

    except Exception as e:
        logger.warning(f"[GeminiSTT] Failed ({e}) — falling back to Whisper.")
        return None

class Transcriber:
    """
    Singleton wrapper for Faster-Whisper.
    Uses ffmpeg to decode WebM/Opus audio before transcription.
    """
    def __init__(self, model_size: str = "base"):
        logger.info(f"Loading Whisper model: {model_size}...")
        try:
            # Try CUDA first for fast transcription
            self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
            # Perform a dummy transcription to force lazy-loading of CUDA DLLs (like cublas64_12.dll)
            dummy_audio = np.zeros(16000, dtype=np.float32)
            list(self.model.transcribe(dummy_audio, vad_filter=False))
            logger.info("Whisper model loaded and verified successfully on CUDA (GPU).")
        except Exception as e:
            logger.warning(f"CUDA verification failed (likely missing DLLs), falling back to CPU. Error: {e}")
            try:
                self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
                logger.info("Whisper model loaded successfully on CPU.")
            except Exception as e2:
                logger.error(f"Failed to load Whisper model on CPU: {e2}")
                self.model = None

    def _convert_webm_to_wav(self, webm_path: str) -> str | None:
        """Convert a WebM/Opus file to WAV using ffmpeg for Whisper compatibility."""
        wav_path = webm_path.replace(".webm", ".wav")
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", webm_path,
                    "-vn",            # Ignore video stream if any
                    "-acodec", "pcm_s16le", # Force PCM 16-bit
                    "-ar", "16000",   # 16kHz sample rate
                    "-ac", "1",       # Mono
                    wav_path
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30
            )
            if result.returncode == 0 and os.path.exists(wav_path):
                return wav_path
        except Exception as e:
            logger.error(f"ffmpeg conversion failed: {e}")
        return None

    async def transcribe(self, audio_data: str | np.ndarray) -> str:
        """
        Transcribe audio from a file path (str) or a float32 PCM numpy array.

        Strategy (dual-engine):
          1. PRIMARY: Gemini Audio Understanding API
             → Perfect for Bengali / Hindi / English / mixed-language speech
          2. FALLBACK: Faster-Whisper (existing engine)
             → Used when Gemini API key is missing or call fails
        """
        import asyncio

        wav_path_to_cleanup = None

        # ── Step 1: Convert WebM → WAV (browser sends WebM/Opus) ────────────
        if isinstance(audio_data, str):
            if audio_data.endswith(".webm"):
                logger.info(f"[Transcriber] Converting audio file: {audio_data}")
                wav_path = await asyncio.to_thread(self._convert_webm_to_wav, audio_data)
                if not wav_path:
                    logger.error("[Transcriber] Audio conversion failed.")
                    return ""
                wav_path_to_cleanup = wav_path
            else:
                # Already a wav file (from native desktop listener)
                wav_path = audio_data
                wav_path_to_cleanup = wav_path

            # Silence check — warn if mic is muted/quiet
            try:
                import wave, struct
                with wave.open(wav_path, "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    samples = struct.unpack(f"<{len(frames)//2}h", frames)
                    max_amp = max(abs(s) for s in samples) if samples else 0
                    logger.info(f"[Transcriber] Max amplitude: {max_amp}/32768")
                    if max_amp < 100:
                        logger.warning(
                            "[Transcriber] Audio is nearly silent — "
                            "ignoring it instead of asking STT to guess."
                        )
                        if wav_path_to_cleanup and os.path.exists(wav_path_to_cleanup):
                            try:
                                os.remove(wav_path_to_cleanup)
                            except Exception:
                                pass
                        return ""
            except Exception as e:
                logger.debug(f"[Transcriber] Amplitude check failed: {e}")

            audio_data = wav_path

        # ── Step 2: Try Gemini STT first (primary engine) ───────────────────
        if isinstance(audio_data, str):  # only for file paths (wav)
            try:
                gemini_text = await _transcribe_with_gemini(audio_data)
                if gemini_text:
                    # Cleanup and return Gemini result
                    if wav_path_to_cleanup and os.path.exists(wav_path_to_cleanup):
                        try:
                            os.remove(wav_path_to_cleanup)
                        except Exception:
                            pass
                    if _is_probable_hallucination(gemini_text):
                        logger.warning(
                            "[Transcriber] Gemini output '%s' looks like a noise "
                            "hallucination — ignoring.",
                            gemini_text.strip(),
                        )
                        return ""
                    return gemini_text
            except Exception as e:
                logger.warning(f"[Transcriber] Gemini STT error: {e} — using Whisper.")

        # ── Step 3: Fallback — Faster-Whisper ──────────────────────────────
        if self.model is None:
            logger.error("[Transcriber] Whisper model not loaded and Gemini failed.")
            return ""

        try:
            def _run_whisper():
                segments, _ = self.model.transcribe(
                    audio_data,
                    beam_size=3,
                    language=None,
                    vad_filter=False,
                    initial_prompt=(
                        "Hello Maya, how are you? Please do this now. "
                        "Maya, kemon acho? Ekhon eta kore dao. "
                        "Namaste Maya, aap kaise hain? Abhi ye kar do. "
                        "The speaker may use English, Bengali, Hindi, or a mix."
                    ),
                )
                return "".join(seg.text for seg in segments)

            text = latinize_transcript(await asyncio.to_thread(_run_whisper))
            logger.info(f"[Transcriber][Whisper] Transcribed: {text}")
        except Exception as e:
            logger.error(f"[Transcriber] Whisper error: {e}")
            text = ""
        finally:
            if wav_path_to_cleanup and os.path.exists(wav_path_to_cleanup):
                try:
                    os.remove(wav_path_to_cleanup)
                except Exception:
                    pass

        if _is_probable_hallucination(text):
            logger.warning(
                "[Transcriber] Whisper output '%s' looks like a noise "
                "hallucination — ignoring.",
                text.strip(),
            )
            return ""

        return text.strip()

transcriber = Transcriber()
