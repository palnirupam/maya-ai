import collections
import numpy as np
import logging

logger = logging.getLogger(__name__)

class AudioBuffer:
    """
    Handles buffering of incoming WebM/Opus audio chunks 
    and handles security limits (max size).
    """
    def __init__(self, max_buffer_seconds: int = 30, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        # Calculate max frames (assuming 1 channel float32)
        self.max_frames = max_buffer_seconds * sample_rate
        self.buffer = collections.deque(maxlen=self.max_frames)
        
    def append(self, pcm_data: np.ndarray):
        """Append decoded PCM float32 data to the buffer."""
        if len(self.buffer) + len(pcm_data) > self.max_frames:
            logger.warning("Audio buffer overflow! Clearing old data.")
            # Keep only the newest data fitting in the buffer
            excess = (len(self.buffer) + len(pcm_data)) - self.max_frames
            for _ in range(excess):
                if self.buffer:
                    self.buffer.popleft()
                    
        self.buffer.extend(pcm_data)

    def get_and_clear(self) -> np.ndarray:
        """Return all buffered data and clear the buffer."""
        data = np.array(self.buffer, dtype=np.float32)
        self.buffer.clear()
        return data

    def clear(self):
        self.buffer.clear()
