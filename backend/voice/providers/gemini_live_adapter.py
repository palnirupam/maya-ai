"""
Gemini Native Audio TTS Adapter.

Uses the Gemini generateContent API with responseModalities=["AUDIO"] to produce
ultra-realistic, human-like speech — exactly like Google AI Studio's voice demos.

Key points:
- Uses the SAME Gemini API key already stored in Maya's database / env var.
- Sentences are sent individually (already batched in handlers.py) so latency stays low.
- Falls back to Edge TTS gracefully on any error.
- Default voice: Leda (calm, sweet, natural female voice).
"""

import base64
import logging
import os
from typing import AsyncGenerator, Optional

import httpx

logger = logging.getLogger(__name__)

# Gemini REST endpoint for Native Audio TTS
# NOTE: gemini-2.0-flash does NOT support audio responseModalities.
# Latest-first Gemini TTS models. Keep the 2.5 fallback because preview model
# availability can differ across free accounts and regions.
_GEMINI_TTS_MODELS = (
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
)
_GEMINI_TTS_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Female voices (recommended)
# Leda  — calm, sweet, elegant        ← default
# Aoede — friendly, energetic
# Kore  — professional, warm
# Male voices available: Puck, Charon, Fenrir, Orus
DEFAULT_VOICE = "Leda"

# System instruction sent alongside every TTS request so Gemini knows
# it should ONLY speak the given text, nothing extra.
_SYSTEM_INSTRUCTION = (
    "You are a voice synthesis engine. "
    "Read the provided text aloud exactly as written — do not add any extra words, "
    "commentary, or modifications. Speak naturally with appropriate emotion and pacing."
)


def _get_api_key() -> Optional[str]:
    """Fetch the Gemini API key — tries DB first, then environment variable."""
    key = None
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
        key = os.getenv("GEMINI_API_KEY")

    if key:
        key_lower = key.lower()
        if any(key_lower.startswith(prefix) for prefix in ("gsk_", "sk-", "nvapi-", "sk-or-")):
            logger.debug(f"[GeminiTTS] API Key appears to be for another provider ({key[:4]}...) — bypassing Gemini TTS.")
            return None
    return key


def _get_voice_name() -> str:
    """Fetch the preferred Gemini voice name from DB, fallback to DEFAULT_VOICE."""
    for module_prefix in ("backend.database", "database"):
        try:
            conn_mod = __import__(f"{module_prefix}.connection", fromlist=["SessionLocal"])
            model_mod = __import__(f"{module_prefix}.models", fromlist=["UserPreferences"])
            db = conn_mod.SessionLocal()
            try:
                pref = db.query(model_mod.UserPreferences).filter(
                    model_mod.UserPreferences.key == "GEMINI_VOICE_NAME"
                ).first()
                if pref and pref.value:
                    return pref.value.strip()
            finally:
                db.close()
        except Exception:
            continue
    return DEFAULT_VOICE


class GeminiLiveAdapter:
    """
    Adapter that calls Gemini's generateContent API with AUDIO modality
    to produce natural, expressive speech from text.

    Drop-in replacement for Edge TTS / ElevenLabs in tts_router.py.
    """

    async def generate_audio_stream(
        self,
        text: str,
        language: str = "en",
        emotion: str = "neutral",
    ) -> AsyncGenerator[bytes, None]:
        """
        Generate audio bytes from text using Gemini Native Audio.
        Yields audio in 4096-byte chunks compatible with the existing WebSocket pipeline.
        Falls back silently (yields nothing) on error so tts_router falls to Edge TTS.
        """
        if not text or not text.strip():
            return

        api_key = _get_api_key()
        if not api_key:
            logger.warning("[GeminiTTS] No API key found — skipping Gemini TTS.")
            return

        voice_name = _get_voice_name()

        speak_text = text.strip()

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": speak_text}],
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for model_name in _GEMINI_TTS_MODELS:
                    response = await client.post(
                        f"{_GEMINI_TTS_BASE_URL}/{model_name}:generateContent",
                        params={"key": api_key},
                        json=payload,
                    )

                    if response.status_code != 200:
                        logger.warning(
                            f"[GeminiTTS] {model_name} API error {response.status_code}: {response.text[:300]}"
                        )
                        continue

                    data = response.json()

                    # Extract base64-encoded audio from response
                    try:
                        inline_data = (
                            data["candidates"][0]["content"]["parts"][0]["inlineData"]
                        )
                        audio_b64: str = inline_data["data"]
                        raw_pcm_bytes = base64.b64decode(audio_b64)

                        # Convert raw PCM16 24kHz to WAV
                        import wave
                        import io
                        with io.BytesIO() as wav_io:
                            with wave.open(wav_io, 'wb') as wav_file:
                                wav_file.setnchannels(1)
                                wav_file.setsampwidth(2) # 16-bit
                                wav_file.setframerate(24000)
                                wav_file.writeframes(raw_pcm_bytes)
                            audio_bytes = wav_io.getvalue()

                    except (KeyError, IndexError, ValueError) as e:
                        logger.error(f"[GeminiTTS] Failed to extract audio from {model_name} response: {e}")
                        logger.debug(f"[GeminiTTS] Response keys: {list(data.keys())}")
                        continue

                    logger.info(
                    f"[GeminiTTS] ✅ Generated {len(audio_bytes)} bytes "
                        f"(model={model_name}, voice={voice_name}, emotion={emotion}, lang={language})"
                    )

                    # Yield in chunks matching the existing pipeline's chunk size
                    chunk_size = 4096
                    for i in range(0, len(audio_bytes), chunk_size):
                        yield audio_bytes[i : i + chunk_size]
                    return

        except httpx.TimeoutException:
            logger.warning("[GeminiTTS] Request timed out — falling back to Edge TTS.")
        except httpx.ConnectError:
            logger.warning("[GeminiTTS] Connection failed — falling back to Edge TTS.")
        except Exception as e:
            logger.error(f"[GeminiTTS] Unexpected error: {e}")
