import logging
import re
import edge_tts
from typing import AsyncGenerator

from ...brain.language_style import detect_language_style, tts_language_for_style

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Language detection (script-based, no external library)
# ──────────────────────────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """Choose a TTS voice for native-script or Latin-script conversation text."""
    return tts_language_for_style(detect_language_style(text))


# ──────────────────────────────────────────────────────────────────────────────
# Emotion → Voice Tuning Map
# Each emotion adjusts pitch, rate, volume for a realistic girlfriend feel
# ──────────────────────────────────────────────────────────────────────────────

EMOTION_TUNING = {
    "happy":    {"pitch": "+8Hz", "rate": "+10%", "volume": "+10%"},
    "sad":      {"pitch": "-8Hz", "rate": "-6%", "volume": "-10%"},
    "angry":    {"pitch": "+14Hz", "rate": "+12%", "volume": "+15%"},
    "cute":     {"pitch": "+10Hz", "rate": "-3%", "volume": "+5%"},
    "romantic": {"pitch": "-5Hz", "rate": "-4%", "volume": "-5%"},
    "neutral":  {"pitch": "+0Hz", "rate": "+0%", "volume": "+0%"},
}

# Maya's voice map
EDGE_VOICE_MAP = {
    "bn": "bn-IN-TanishaaNeural",
    "hi": "hi-IN-SwaraNeural",
    "en": "en-IN-NeerjaExpressiveNeural",
}
EDGE_DEFAULT_VOICE = "en-IN-NeerjaExpressiveNeural"


# ──────────────────────────────────────────────────────────────────────────────
# ElevenLabs stub — kept for API compatibility with settings route
# ──────────────────────────────────────────────────────────────────────────────

class ElevenLabsTTSAdapter:
    """Disabled — ElevenLabs requires paid plan for library voices."""
    def __init__(self, *args, **kwargs):
        pass

    async def generate_audio_stream(self, text: str, language: str = "en") -> AsyncGenerator[bytes, None]:
        return
        yield  # make it a generator


# ──────────────────────────────────────────────────────────────────────────────
# Edge TTS — emotional voice with native parameters
# ──────────────────────────────────────────────────────────────────────────────

class EdgeTTSAdapter:
    """
    Microsoft Edge TTS with emotional native tuning parameters.
    Maya speaks softly, expressively, like a real Bengali girlfriend.
    """

    async def generate_audio_stream(
        self,
        text: str,
        language: str = "en",
        emotion: str = "neutral"
    ) -> AsyncGenerator[bytes, None]:
        if not text.strip():
            return

        voice = EDGE_VOICE_MAP.get(language, EDGE_DEFAULT_VOICE)
        tuning = EMOTION_TUNING.get(emotion, EMOTION_TUNING["neutral"])
        
        rate = tuning["rate"]
        pitch = tuning["pitch"]
        volume = tuning["volume"]

        logger.info(f"Edge TTS → lang={language}, voice={voice}, emotion={emotion}, rate={rate}, pitch={pitch}, volume={volume}")

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                pitch=pitch,
                volume=volume
            )
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        except Exception as e:
            logger.error(f"Edge TTS error (voice={voice}, emotion={emotion}): {e}")
            # Plain fallback without emotion tuning, using the CORRECT voice (not hardcoded default voice)
            try:
                communicate = edge_tts.Communicate(text, voice)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        yield chunk["data"]
            except Exception as e2:
                logger.error(f"Edge TTS fallback also failed: {e2}")
