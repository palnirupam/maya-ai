from backend.api.telegram_bot import TelegramBotManager
from backend.voice.input.desktop_listener import (
    DEFAULT_NATIVE_MIC_LOCKED,
    MIN_BARGE_IN_THRESHOLD,
    DesktopMicrophoneListener,
)
from backend.voice.voice_state_machine import VoiceStateMachine


def _listener_without_audio_dependencies() -> DesktopMicrophoneListener:
    listener = DesktopMicrophoneListener.__new__(DesktopMicrophoneListener)
    listener._is_locked = False
    listener._remote_suppression_count = 0
    return listener


def test_native_microphone_defaults_to_locked(monkeypatch) -> None:
    from backend.voice.vad import silero

    monkeypatch.setattr(silero, "vad", object())
    listener = DesktopMicrophoneListener(state_machine=object())

    assert DEFAULT_NATIVE_MIC_LOCKED is True
    assert listener.is_locked
    assert listener.is_manually_locked


def test_silent_calibration_keeps_nonzero_threshold() -> None:
    import numpy as np

    class SilentStream:
        def read(self, samples):
            return np.zeros((samples, 1), dtype=np.float32), False

    listener = _listener_without_audio_dependencies()
    listener._stream = SilentStream()
    listener._barge_in_threshold = 0.02

    listener._calibrate_ambient_noise()

    assert listener._barge_in_threshold == MIN_BARGE_IN_THRESHOLD


def test_remote_suppression_does_not_change_manual_lock() -> None:
    listener = _listener_without_audio_dependencies()

    listener.suppress_remote_input()
    assert listener.is_locked
    assert not listener.is_manually_locked

    listener.lock()
    listener.resume_remote_input()
    assert listener.is_locked
    assert listener.is_manually_locked

    listener.unlock()
    assert not listener.is_locked


def test_duplicate_telegram_update_is_rejected() -> None:
    manager = TelegramBotManager()

    assert manager._claim_update(101)
    assert not manager._claim_update(101)
    assert manager._claim_update(102)


def test_telegram_dashboard_has_mic_controls() -> None:
    keyboard = TelegramBotManager._default_keyboard()["keyboard"]
    button_texts = {button["text"] for row in keyboard for button in row}

    assert "🔒 Mic Lock" in button_texts
    assert "🔓 Mic Unlock" in button_texts


def test_discard_queued_voice_audio_removes_pending_file(tmp_path) -> None:
    state_machine = VoiceStateMachine()
    audio_path = tmp_path / "pending.wav"
    audio_path.write_bytes(b"voice")
    state_machine._audio_queue.put_nowait(str(audio_path))

    assert state_machine.discard_queued_audio() == 1
    assert state_machine._audio_queue.empty()
    assert not audio_path.exists()


def test_discard_queued_voice_audio_handles_empty_queue() -> None:
    state_machine = VoiceStateMachine()

    assert state_machine.discard_queued_audio() == 0
    assert state_machine._audio_queue.empty()
