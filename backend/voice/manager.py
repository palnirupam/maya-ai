import logging
from typing import AsyncGenerator

# Existing router
from .output.tts_router import tts_router
# New modules
from .providers.gpt_sovits_adapter import GPTSoVITSAdapter
from .emotions.formatter import formatter
from .playback.player import player

logger = logging.getLogger(__name__)

class VoiceManager:
    """
    High-level orchestrator for Maya's Voice Engine.
    It prefers the local GPT-SoVITS engine if running, otherwise
    falls back to the existing tts_router (ElevenLabs/EdgeTTS).
    """
    def __init__(self):
        self.gpt_sovits = GPTSoVITSAdapter()
        self.use_advanced_engine = False

    async def initialize(self):
        """Check availability of advanced local engines."""
        is_running = await self.gpt_sovits.check_health()
        if is_running:
            logger.info("🎙️ GPT-SoVITS engine detected. Enabling advanced emotional voice pipeline.")
            self.use_advanced_engine = True
        else:
            logger.info("ℹ️ GPT-SoVITS engine not running. Defaulting to standard TTS Router.")
            self.use_advanced_engine = False

    async def speak(self, raw_text: str, language: str = "bn") -> AsyncGenerator[bytes, None]:
        """
        Process the text, extract emotions, generate audio, and stream it.
        Yields audio chunks for websocket streaming.
        """
        # 1. Format text and extract emotions
        emotion = formatter.extract_emotion(raw_text)
        clean_text = formatter.format_text(raw_text)
        
        if not clean_text:
            return

        logger.debug(f"Maya speaking [{emotion}]: {clean_text}")

        # 2. Route to the best available engine
        if self.use_advanced_engine:
            async for chunk in self.gpt_sovits.generate_audio_stream(clean_text, language, emotion):
                await player.add_chunk(chunk)
                yield chunk
        else:
            async for chunk in tts_router.stream_audio(clean_text, language, emotion):
                yield chunk

voice_manager = VoiceManager()
