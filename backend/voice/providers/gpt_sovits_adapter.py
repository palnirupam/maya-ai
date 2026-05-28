import os
import logging
import httpx
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# GPT-SoVITS v2/v4 supported languages — Bengali and Hindi are NOT supported
# For bn/hi → falls back to Edge TTS automatically
SUPPORTED_LANGS = {"en", "zh", "ja", "ko", "yue", "auto"}

class GPTSoVITSAdapter:
    """
    Adapter for connecting to a local GPT-SoVITS API endpoint.
    NOTE: GPT-SoVITS v2 does NOT support Bengali (bn).
    For Bengali text, this adapter returns nothing and lets the router fall back to Edge TTS.
    """
    def __init__(self, api_url: str = "http://127.0.0.1:9880", ref_audio_path: str = None, prompt_text: str = None, prompt_lang: str = "zh"):
        self.api_url = api_url
        self.ref_audio_path = ref_audio_path or os.getenv("GPT_SOVITS_REF_AUDIO", "C:/maya-ai/test_nabanita.mp3")
        # Prompt text must be in a supported language — use Chinese/English placeholder
        self.prompt_text = prompt_text or os.getenv("GPT_SOVITS_PROMPT_TEXT", "Hello, how are you?")
        self.prompt_lang = prompt_lang  # "zh" or "en" — must match prompt_text language
        self.is_available = False
        logger.debug(f"GPT-SoVITS adapter initialized at {self.api_url}")

    async def check_health(self) -> bool:
        """Check if the local GPT-SoVITS server is running."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # Hitting /openapi.json returns 200 when the FastAPI server is running, avoiding 400 Bad Request logs
                resp = await client.get(f"{self.api_url}/openapi.json")
                self.is_available = resp.status_code == 200
                return self.is_available
        except Exception:
            self.is_available = False
            return False

    async def generate_audio_stream(self, text: str, language: str = "en", emotion: str = "neutral") -> AsyncGenerator[bytes, None]:
        """
        Stream audio from the local GPT-SoVITS API.
        Bengali (bn) is NOT supported by GPT-SoVITS v2 — yields nothing so router falls back to Edge TTS.
        """
        if not text.strip():
            return

        # GPT-SoVITS v2 does not support Bengali — skip and let Edge TTS handle it
        if language not in SUPPORTED_LANGS:
            logger.info(f"GPT-SoVITS: language '{language}' not supported. Skipping → Edge TTS will handle.")
            return

        params = {
            "text": text,
            "text_lang": language,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "media_type": "wav",
            "streaming_mode": "false",  # Crucial: Must be false to ensure valid WAV headers are generated
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("GET", f"{self.api_url}/tts", params=params) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.error(f"GPT-SoVITS Error: {response.status_code} - {body}")
                        return

                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield chunk
        except httpx.ConnectError:
            logger.warning("GPT-SoVITS local server is not running.")
        except Exception as e:
            logger.error(f"GPT-SoVITS Streaming Error: {e}")
