import logging
from typing import AsyncGenerator

from .edge_tts_adapter import EdgeTTSAdapter, detect_language
from ..providers.gpt_sovits_adapter import GPTSoVITSAdapter
from .elevenlabs import ElevenLabsAdapter
from ..emotions.formatter import formatter
from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences
from backend.database.crypto import crypto_manager

logger = logging.getLogger(__name__)


class TTSRouter:
    """
    Smart TTS router:
      Allows selection of a primary TTS provider:
      - 'edge': Microsoft Edge TTS (built-in, free, fast)
      - 'elevenlabs': ElevenLabs / cvoice.ai (cloud voice clone)
      - 'gpt_sovits': GPT-SoVITS (local offline voice clone)
    """

    def __init__(self):
        self._edge = EdgeTTSAdapter()
        self._gpt_sovits = GPTSoVITSAdapter()
        self._elevenlabs = ElevenLabsAdapter()
        self.primary_provider = "edge"
        self.reload_key()

    def reload_key(self):
        """Reloads credentials and TTS provider configuration from database."""
        try:
            self._elevenlabs.reload_key()
        except Exception as e:
            logger.error(f"Failed to reload ElevenLabs keys in TTS Router: {e}")

        db = SessionLocal()
        try:
            pref = db.query(UserPreferences).filter(UserPreferences.key == "TTS_PRIMARY_PROVIDER").first()
            if pref and pref.value:
                try:
                    self.primary_provider = crypto_manager.decrypt(pref.value).strip()
                except Exception:
                    self.primary_provider = "edge"
            else:
                if self._elevenlabs.api_key:
                    self.primary_provider = "elevenlabs"
                else:
                    self.primary_provider = "edge"
            logger.info(f"TTS Router reloaded. Primary TTS Provider: {self.primary_provider}")
        except Exception as e:
            logger.error(f"Failed to reload primary TTS provider: {e}")
            self.primary_provider = "edge"
        finally:
            db.close()

    async def stream_audio(
        self, text: str, language: str | None = None, emotion: str | None = None
    ) -> AsyncGenerator[bytes, None]:
        if not text or not text.strip():
            return

        lang = language or detect_language(text)

        # Extract emotion and clean text
        extracted_emotion = formatter.extract_emotion(text)
        emotion = emotion or extracted_emotion or "neutral"
        clean_text = formatter.format_text(text)

        if not clean_text:
            return

        primary = getattr(self, "primary_provider", "edge")

        # 1. ElevenLabs / cvoice.ai
        if primary == "elevenlabs":
            if self._elevenlabs.api_key:
                try:
                    has_audio = False
                    async for chunk in self._elevenlabs.generate_audio_stream(clean_text, lang):
                        has_audio = True
                        yield chunk
                    if has_audio:
                        return
                except Exception as e:
                    logger.warning(f"ElevenLabs stream failed: {e}. Falling back to Edge TTS.")
            else:
                logger.warning("ElevenLabs primary selected but API key is missing. Falling back to Edge TTS.")

        # 2. GPT-SoVITS
        elif primary == "gpt_sovits":
            import time
            now = time.time()
            if hasattr(self, '_gpt_down_until') and now < self._gpt_down_until:
                pass
            elif await self._gpt_sovits.check_health():
                logger.info("GPT-SoVITS healthy — using local AI voice engine.")
                try:
                    has_audio = False
                    async for chunk in self._gpt_sovits.generate_audio_stream(clean_text, lang, emotion):
                        has_audio = True
                        yield chunk
                    if has_audio:
                        return
                except Exception as e:
                    logger.warning(f"GPT-SoVITS stream failed: {e}. Falling back to Edge TTS.")
            else:
                self._gpt_down_until = now + 5.0
                logger.info("GPT-SoVITS not ready — using Edge TTS fallback.")

        # 3. Default/Fallback: Edge TTS
        async for chunk in self._edge.generate_audio_stream(clean_text, lang, emotion):
            yield chunk



tts_router = TTSRouter()
