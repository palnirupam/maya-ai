import asyncio
import logging

logger = logging.getLogger(__name__)

class AudioPlayer:
    """
    Manages a queue of audio chunks to ensure gapless playback.
    In a fully realtime system, this might send audio directly to PyAudio 
    or stream it over WebSockets to the frontend.
    """
    def __init__(self):
        self.queue = asyncio.Queue()
        self.is_playing = False
        self._play_task = None
        
    async def add_chunk(self, chunk: bytes):
        """Add an audio chunk to the playback queue."""
        await self.queue.put(chunk)
        if not self.is_playing:
            self._play_task = asyncio.create_task(self._playback_loop())
            
    async def _playback_loop(self):
        self.is_playing = True
        logger.debug("Started audio playback loop.")
        try:
            while True:
                # Wait for next chunk (with a timeout so we don't hang forever if done)
                try:
                    chunk = await asyncio.wait_for(self.queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    break # Queue is empty and timed out
                    
                # In a real desktop app, we would write to PyAudio here
                # e.g., pyaudio_stream.write(chunk)
                # For websocket apps, we might just yield it.
                # Right now, we simulate playing:
                await asyncio.sleep(0.01) 
                
                self.queue.task_done()
        except Exception as e:
            logger.error(f"Playback loop error: {e}")
        finally:
            self.is_playing = False
            logger.debug("Playback loop finished.")

player = AudioPlayer()
