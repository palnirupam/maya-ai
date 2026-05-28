import logging
import numpy as np
from typing import Callable, Awaitable
from ..vad.silero import vad
from ..streaming.buffer import AudioBuffer

logger = logging.getLogger(__name__)

class AudioPipeline:
    """
    Manages the flow of audio: 
    Raw Bytes -> Decode -> VAD -> Buffer -> Transcriber trigger
    """
    def __init__(self, session_id: str, on_speech_end: Callable[[np.ndarray], Awaitable[None]]):
        self.session_id = session_id
        self.buffer = AudioBuffer()
        self.on_speech_end = on_speech_end
        self.is_user_speaking = False
        self.silence_chunks_count = 0
        self.MAX_SILENCE_CHUNKS = 3 # Triggers transcription after ~750ms silence

    async def process_chunk(self, pcm_data: np.ndarray):
        """
        Process an incoming PCM chunk. 
        If VAD detects speech, add to buffer.
        If VAD detects silence after speech, trigger transcription.
        """
        has_speech = vad.is_speech(pcm_data)
        
        if has_speech:
            self.is_user_speaking = True
            self.silence_chunks_count = 0
            self.buffer.append(pcm_data)
        elif self.is_user_speaking:
            # Silence detected after speech
            self.silence_chunks_count += 1
            self.buffer.append(pcm_data) # Keep trailing silence for context
            
            if self.silence_chunks_count >= self.MAX_SILENCE_CHUNKS:
                # User has stopped speaking
                self.is_user_speaking = False
                self.silence_chunks_count = 0
                full_audio = self.buffer.get_and_clear()
                
                logger.info(f"Speech ended. Sending {len(full_audio)} samples to transcriber.")
                await self.on_speech_end(full_audio)
