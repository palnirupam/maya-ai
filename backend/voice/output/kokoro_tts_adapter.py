import asyncio
import io
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

KOKORO_VOICE_MAP: dict[str, dict[str, str]] = {
    "bn": {"lang": "hi", "voice": "hf_alpha"},
    "hi": {"lang": "hi", "voice": "hf_alpha"},
    "en": {"lang": "en-us", "voice": "af_heart"},
}
_KOKORO_DEFAULT: dict[str, str] = {"lang": "en-us", "voice": "af_heart"}

EMOTION_SPEED_MAP: dict[str, float] = {
    "happy":    1.12,
    "sad":      0.90,
    "angry":    1.15,
    "cute":     0.95,
    "romantic": 0.88,
    "neutral":  1.0,
}

_MODEL_DIR  = Path(__file__).parent / "kokoro_models"
_ONNX_MODEL = _MODEL_DIR / "kokoro-v1.0.onnx"
_VOICES_BIN = _MODEL_DIR / "voices-v1.0.bin"

_RELEASE_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_MODEL_URL  = f"{_RELEASE_BASE}/kokoro-v1.0.onnx"
_VOICES_URL = f"{_RELEASE_BASE}/voices-v1.0.bin"


class KokoroTTSAdapter:

    def __init__(self) -> None:
        self.disabled: bool = False
        self._kokoro = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kokoro")
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        try:
            import kokoro_onnx  # noqa: F401
            import soundfile    # noqa: F401
        except ImportError as e:
            self.disabled = True
            logger.warning("Kokoro TTS disabled — package missing: %s. Fix: pip install kokoro-onnx soundfile", e)
            return
        logger.info("Kokoro TTS: packages OK ✓ (model loads on first use)")

    def _download_file(self, url: str, dest: Path) -> None:
        import urllib.request
        logger.info("Kokoro TTS: downloading %s …", dest.name)
        urllib.request.urlretrieve(url, dest)
        logger.info("Kokoro TTS: %s downloaded ✓", dest.name)

    def _ensure_model_files(self) -> bool:
        try:
            _MODEL_DIR.mkdir(parents=True, exist_ok=True)
            if not _ONNX_MODEL.exists():
                self._download_file(_MODEL_URL, _ONNX_MODEL)
            if not _VOICES_BIN.exists():
                self._download_file(_VOICES_URL, _VOICES_BIN)
            return True
        except Exception as e:
            logger.warning("Kokoro TTS: model download failed: %s", e)
            return False

    def _get_kokoro(self):
        if self._kokoro is None:
            if not self._ensure_model_files():
                raise RuntimeError("Kokoro model files unavailable.")
            from kokoro_onnx import Kokoro
            logger.debug("Kokoro TTS: loading ONNX model …")
            self._kokoro = Kokoro(str(_ONNX_MODEL), str(_VOICES_BIN))
            logger.info("Kokoro TTS: ONNX model ready ✓")
        return self._kokoro

    @staticmethod
    def _compress_silence(arr, sample_rate: int = 24000, max_silence_ms: int = 500, threshold: float = 0.003):
        import numpy as np
        max_samp = int(max_silence_ms * sample_rate / 1000)
        frame_len = 240
        out = []
        silent_acc = 0
        for i in range(0, len(arr), frame_len):
            chunk = arr[i : i + frame_len]
            if np.sqrt(np.mean(chunk ** 2) + 1e-12) < threshold:
                silent_acc += len(chunk)
                if silent_acc <= max_samp:
                    out.append(chunk)
            else:
                silent_acc = 0
                out.append(chunk)
        return np.concatenate(out) if out else arr

    @staticmethod
    def _to_wav_bytes(samples, sample_rate: int) -> bytes:
        import soundfile as sf
        import numpy as np
        # Convert list to numpy array if necessary
        if not isinstance(samples, np.ndarray):
            samples = np.array(samples, dtype=np.float32)
            
        # Apply silence compression to remove unnaturally long Kokoro pauses
        samples = KokoroTTSAdapter._compress_silence(samples, sample_rate)
        
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV")
        return buf.getvalue()

    async def generate_audio_stream(
        self,
        text: str,
        language: str = "en",
        emotion: str = "neutral",
    ) -> AsyncGenerator[bytes, None]:
        if self.disabled:
            return

        cfg = KOKORO_VOICE_MAP.get(language, _KOKORO_DEFAULT)
        processed = _latinize_for_kokoro(text)
        if not processed.strip():
            return

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _producer() -> None:
            try:
                kokoro = self._get_kokoro()
                speed = EMOTION_SPEED_MAP.get(emotion, 1.0)
                samples, sample_rate = kokoro.create(
                    processed,
                    voice=cfg["voice"],
                    speed=speed,
                    lang=cfg["lang"],
                )
                wav = self._to_wav_bytes(samples, sample_rate)
                loop.call_soon_threadsafe(queue.put_nowait, wav)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        future = loop.run_in_executor(self._executor, _producer)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    logger.debug("Kokoro TTS error: %s", item)
                    break
                yield item
        finally:
            await future


def _latinize_for_kokoro(text: str) -> str:
    try:
        from backend.brain.language_style import latinize_transcript
        return latinize_transcript(text)
    except Exception:
        return text
