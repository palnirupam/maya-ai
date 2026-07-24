import logging
from typing import AsyncGenerator

from .edge_tts_adapter import EdgeTTSAdapter, detect_language
from ..providers.gpt_sovits_adapter import GPTSoVITSAdapter
from ..providers.gemini_live_adapter import GeminiLiveAdapter
from .elevenlabs import ElevenLabsAdapter
from ..emotions.formatter import formatter
from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences
from backend.database.crypto import crypto_manager

logger = logging.getLogger(__name__)


# Valid TTS provider identifiers.
_VALID_TTS_PROVIDERS = frozenset({"edge", "gemini", "elevenlabs", "gpt_sovits"})

# Edge TTS is the default: zero-latency, zero-API-dependency, always available.
# Users can switch to Gemini Native Audio / ElevenLabs / GPT-SoVITS from Settings.
_DEFAULT_TTS_PROVIDER = "edge"


class TTSRouter:
    """
    Smart TTS router with graceful fallback chain:
      Primary (user-configurable, default: Edge TTS)
        → Fallback: Edge TTS (always available, ~50ms latency)

    Provider options:
      - 'edge'       : Microsoft Edge TTS — free, fast, offline-capable  [DEFAULT]
      - 'gemini'     : Gemini Native Audio — ultra-realistic, cloud-only
      - 'elevenlabs' : ElevenLabs / cvoice.ai — voice clone, cloud-only
      - 'gpt_sovits' : GPT-SoVITS — local offline voice clone
    """

    def __init__(self):
        self._edge = EdgeTTSAdapter()
        self._gpt_sovits = GPTSoVITSAdapter()
        self._elevenlabs = ElevenLabsAdapter()
        self._gemini = GeminiLiveAdapter()
        self.primary_provider = _DEFAULT_TTS_PROVIDER
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
                    stored = crypto_manager.decrypt(pref.value).strip()
                    # Accept any valid provider the user explicitly chose.
                    # Fall back to the default if the stored value is unrecognised.
                    if stored in _VALID_TTS_PROVIDERS:
                        self.primary_provider = stored
                    else:
                        logger.warning(
                            f"Unknown TTS provider '{stored}' in preferences — "
                            f"reverting to default '{_DEFAULT_TTS_PROVIDER}'."
                        )
                        self.primary_provider = _DEFAULT_TTS_PROVIDER
                except Exception:
                    self.primary_provider = _DEFAULT_TTS_PROVIDER
            else:
                self.primary_provider = _DEFAULT_TTS_PROVIDER
            logger.info(f"TTS Router reloaded. Primary TTS Provider: {self.primary_provider}")
        except Exception as e:
            logger.error(f"Failed to reload primary TTS provider: {e}")
            self.primary_provider = _DEFAULT_TTS_PROVIDER
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

        primary = getattr(self, "primary_provider", "gemini")

        # 1. Gemini Native Audio (default — ultra-realistic human-like voice)
        if primary == "gemini":
            try:
                has_audio = False
                async for chunk in self._gemini.generate_audio_stream(clean_text, lang, emotion):
                    has_audio = True
                    yield chunk
                if has_audio:
                    return
                logger.warning("Gemini TTS yielded no audio — falling back to Edge TTS.")
            except Exception as e:
                logger.warning(f"Gemini TTS stream failed: {e}. Falling back to Edge TTS.")

        # 2. ElevenLabs / cvoice.ai
        elif primary == "elevenlabs":
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
