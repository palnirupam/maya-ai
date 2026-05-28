import os
import logging
import httpx
from typing import AsyncGenerator
from backend.database.connection import SessionLocal
from backend.database.models import UserPreferences
from backend.database.crypto import crypto_manager

logger = logging.getLogger(__name__)

class ElevenLabsAdapter:
    """
    Adapter for ElevenLabs Voice Cloning API.
    Streams TTS audio bytes for a given text.
    """
    def __init__(self):
        self.api_key = None
        self.voice_id = None
        self.model_id = None
        self.reload_key()

    def reload_key(self):
        """Loads ElevenLabs credentials and settings from the database (decrypted)."""
        db = SessionLocal()
        try:
            # 1. API Key
            key_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_API_KEY").first()
            if key_pref and key_pref.value:
                try:
                    self.api_key = crypto_manager.decrypt(key_pref.value).strip()
                except Exception as e:
                    logger.error(f"Failed to decrypt ELEVENLABS_API_KEY: {e}")
                    self.api_key = None
            else:
                self.api_key = os.getenv("ELEVENLABS_API_KEY")

            # 2. Voice ID
            voice_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_VOICE_ID").first()
            if voice_pref and voice_pref.value:
                try:
                    self.voice_id = crypto_manager.decrypt(voice_pref.value).strip()
                except Exception as e:
                    logger.error(f"Failed to decrypt ELEVENLABS_VOICE_ID: {e}")
                    self.voice_id = "21m00Tcm4TlvDq8ikWAM" # default Rachel voice
            else:
                self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

            # 3. Model ID
            model_pref = db.query(UserPreferences).filter(UserPreferences.key == "ELEVENLABS_MODEL_ID").first()
            if model_pref and model_pref.value:
                try:
                    self.model_id = crypto_manager.decrypt(model_pref.value).strip()
                except Exception:
                    self.model_id = "eleven_multilingual_v2"
            else:
                self.model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

            if self.api_key:
                logger.info(f"ElevenLabs Adapter configured. Voice ID: {self.voice_id}, Model: {self.model_id}")
            else:
                logger.warning("No ElevenLabs API Key found. ElevenLabs TTS will be disabled.")
        finally:
            db.close()

    async def generate_audio_stream(self, text: str, language: str = "en") -> AsyncGenerator[bytes, None]:
        """
        Calls ElevenLabs or cvoice.ai stream endpoint to generate and stream audio bytes for text.
        """
        if not self.api_key or not self.voice_id:
            logger.warning("Voice/TTS API: API Key or Voice ID not configured.")
            return

        if not text.strip():
            return

        # 1. cvoice.ai Integration
        if self.api_key.startswith("cvai_"):
            url = "https://cvoice.ai/api/tts"
            headers = {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "voice_id": self.voice_id,
                "text": text
            }
            try:
                logger.info(f"cvoice.ai TTS: Requesting audio URL for '{text[:30]}...' using voice {self.voice_id}")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.error(f"cvoice.ai Error {response.status_code}: {body.decode('utf-8', errors='ignore')}")
                        return
                    
                    data = response.json()
                    audio_url = data.get("url")
                    if not audio_url:
                        logger.error(f"cvoice.ai Error: 'url' key missing in response: {data}")
                        return
                        
                    # Stream the audio bytes from the audio URL
                    logger.info(f"cvoice.ai TTS: Streaming audio from {audio_url}")
                    async with client.stream("GET", audio_url) as audio_response:
                        if audio_response.status_code != 200:
                            logger.error(f"Failed to fetch audio from cvoice.ai URL: {audio_response.status_code}")
                            return
                        async for chunk in audio_response.aiter_bytes(chunk_size=4096):
                            if chunk:
                                yield chunk
            except Exception as e:
                logger.error(f"cvoice.ai Stream Exception: {e}")
            return

        # 2. ElevenLabs Integration
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "accept": "audio/mpeg"
        }
        
        # Use eleven_multilingual_v2 for Hindi (as it is supported)
        # and eleven_v3 for Bengali (as multilingual_v2 does NOT support Bengali)
        model = self.model_id
        if language == "hi" and model != "eleven_multilingual_v2":
            model = "eleven_multilingual_v2"
        elif language == "bn":
            model = "eleven_v3"

        payload = {
            "text": text,
            "model_id": model,
            "voice_settings": {
                "stability": 0.65, # Raised to prevent stuttering/hallucinating in Bengali
                "similarity_boost": 0.75
            }
        }

        # Request 128kbps MP3 stream
        params = {
            "output_format": "mp3_44100_128"
        }

        try:
            logger.info(f"ElevenLabs TTS: Generating stream for '{text[:30]}...' using model {model}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload, params=params) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.error(f"ElevenLabs Error {response.status_code}: {body.decode('utf-8', errors='ignore')}")
                        return

                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if chunk:
                            yield chunk
        except Exception as e:
            logger.error(f"ElevenLabs Stream Exception: {e}")
