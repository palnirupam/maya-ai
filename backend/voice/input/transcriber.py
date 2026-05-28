import logging
import numpy as np
import subprocess
import os
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

class Transcriber:
    """
    Singleton wrapper for Faster-Whisper.
    Uses ffmpeg to decode WebM/Opus audio before transcription.
    """
    def __init__(self, model_size: str = "base"):
        logger.info(f"Loading Whisper model: {model_size}...")
        try:
            # Try CUDA first for fast transcription
            self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
            # Perform a dummy transcription to force lazy-loading of CUDA DLLs (like cublas64_12.dll)
            dummy_audio = np.zeros(16000, dtype=np.float32)
            list(self.model.transcribe(dummy_audio, vad_filter=False))
            logger.info("Whisper model loaded and verified successfully on CUDA (GPU).")
        except Exception as e:
            logger.warning(f"CUDA verification failed (likely missing DLLs), falling back to CPU. Error: {e}")
            try:
                self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
                logger.info("Whisper model loaded successfully on CPU.")
            except Exception as e2:
                logger.error(f"Failed to load Whisper model on CPU: {e2}")
                self.model = None

    def _convert_webm_to_wav(self, webm_path: str) -> str | None:
        """Convert a WebM/Opus file to WAV using ffmpeg for Whisper compatibility."""
        wav_path = webm_path.replace(".webm", ".wav")
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", webm_path,
                    "-vn",            # Ignore video stream if any
                    "-acodec", "pcm_s16le", # Force PCM 16-bit
                    "-ar", "16000",   # 16kHz sample rate
                    "-ac", "1",       # Mono
                    wav_path
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30
            )
            if result.returncode == 0 and os.path.exists(wav_path):
                return wav_path
        except Exception as e:
            logger.error(f"ffmpeg conversion failed: {e}")
        return None

    async def transcribe(self, audio_data: str | np.ndarray) -> str:
        """
        Transcribe audio from a file path (str) or a float32 PCM numpy array.
        If a file path is given, converts WebM to WAV first via ffmpeg.
        Returns the transcribed text.
        """
        if self.model is None:
            return ""

        try:
            import asyncio

            wav_path_to_cleanup = None

            # If given a file path (WebM from browser), convert to WAV first
            if isinstance(audio_data, str):
                logger.info(f"Converting audio file: {audio_data}")
                wav_path = await asyncio.to_thread(self._convert_webm_to_wav, audio_data)
                if not wav_path:
                    logger.error("Audio conversion failed, cannot transcribe.")
                    return ""
                
                # DIAGNOSTIC: Check if the audio is completely silent
                try:
                    import wave
                    import struct
                    with wave.open(wav_path, 'rb') as wf:
                        frames = wf.readframes(wf.getnframes())
                        samples = struct.unpack(f"<{len(frames)//2}h", frames)
                        max_amp = max(abs(s) for s in samples) if samples else 0
                        logger.info(f"DIAGNOSTIC: Max audio amplitude is {max_amp} (Max possible: 32768)")
                        if max_amp < 100:
                            logger.warning("WARNING: The audio is almost completely silent! The user's microphone might be muted or the wrong device is selected in Windows.")
                except Exception as e:
                    logger.error(f"Failed to check audio volume: {e}")

                audio_data = wav_path
                wav_path_to_cleanup = wav_path

            def _run_transcription():
                segments, info = self.model.transcribe(
                    audio_data,
                    beam_size=3,
                    language=None,    
                    vad_filter=False,  # Disabled because it might be aggressively cutting out the user's voice
                    # vad_parameters=dict(min_silence_duration_ms=1000, speech_pad_ms=400),
                    initial_prompt="হ্যালো মায়া, কেমন আছো? नमस्ते माया, आप कैसे हैं? Hello Maya, how are you doing?" # Biases the model to Bengali/Hindi/English
                )
                return "".join([segment.text for segment in segments])

            text = await asyncio.to_thread(_run_transcription)

            # Cleanup converted WAV
            if wav_path_to_cleanup and os.path.exists(wav_path_to_cleanup):
                try:
                    os.remove(wav_path_to_cleanup)
                except:
                    pass

            return text.strip()
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""

transcriber = Transcriber()
