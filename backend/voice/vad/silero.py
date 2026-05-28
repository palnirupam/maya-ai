import torch
import numpy as np
import logging

logger = logging.getLogger(__name__)

class SileroVAD:
    """
    Wrapper for Silero VAD to detect speech in audio chunks.
    """
    def __init__(self, threshold: float = 0.5, sampling_rate: int = 16000):
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        try:
            self.model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True
            )
            self.get_speech_timestamps = utils[0]
            logger.info("Silero VAD loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load Silero VAD: {e}")
            self.model = None

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """
        Check if the audio chunk contains speech above the threshold.
        audio_chunk should be a 1D numpy array of float32 values between -1.0 and 1.0.
        """
        if self.model is None:
            # Fallback if model failed to load
            return True
            
        try:
            # Convert numpy array to torch tensor
            tensor = torch.from_numpy(audio_chunk)
            
            # Use get_speech_timestamps which handles arbitrary chunk sizes automatically
            timestamps = self.get_speech_timestamps(
                tensor, 
                self.model, 
                sampling_rate=self.sampling_rate,
                threshold=self.threshold
            )
            return len(timestamps) > 0
        except Exception as e:
            logger.error(f"VAD prediction error: {e}")
            return False

vad = SileroVAD()
