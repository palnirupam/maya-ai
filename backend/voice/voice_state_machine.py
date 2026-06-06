"""
Maya Voice State Machine
========================
Central coordinator for the native desktop voice engine.

Responsibilities:
  - Enforce the state transition table (invalid transitions are blocked + logged)
  - Own all queue rejection logic (State Machine, not the Audio Queue)
  - Manage asyncio cancellation tokens for the LLM
  - Log per-request latency metrics into a ring buffer (last 1000 requests)
  - Expose /voice/stats endpoint data
"""

import asyncio
import logging
import time
from collections import deque
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


# ── States ─────────────────────────────────────────────────────────────────────

class VoiceState(Enum):
    IDLE         = auto()
    LISTENING    = auto()
    TRANSCRIBING = auto()
    THINKING     = auto()
    SPEAKING     = auto()
    INTERRUPTED  = auto()


# ── Valid Transition Table ──────────────────────────────────────────────────────
# True = allowed, False = blocked
_TRANSITIONS: dict[VoiceState, set[VoiceState]] = {
    VoiceState.IDLE:         {VoiceState.LISTENING},
    VoiceState.LISTENING:    {VoiceState.IDLE, VoiceState.TRANSCRIBING},
    VoiceState.TRANSCRIBING: {VoiceState.THINKING, VoiceState.INTERRUPTED, VoiceState.LISTENING},
    VoiceState.THINKING:     {VoiceState.SPEAKING, VoiceState.INTERRUPTED},
    VoiceState.SPEAKING:     {VoiceState.LISTENING, VoiceState.INTERRUPTED},
    VoiceState.INTERRUPTED:  {VoiceState.IDLE, VoiceState.LISTENING},
}


# ── Metric record ───────────────────────────────────────────────────────────────

class RequestMetric:
    __slots__ = ("vad_ms", "stt_ms", "llm_ms", "tts_ms", "e2e_ms", "ts")

    def __init__(self):
        self.vad_ms = self.stt_ms = self.llm_ms = self.tts_ms = self.e2e_ms = 0.0
        self.ts = time.time()

    def to_dict(self) -> dict:
        return {
            "timestamp": self.ts,
            "vad_ms":    self.vad_ms,
            "stt_ms":    self.stt_ms,
            "llm_ms":    self.llm_ms,
            "tts_ms":    self.tts_ms,
            "e2e_ms":    self.e2e_ms,
        }


# ── State Machine ───────────────────────────────────────────────────────────────

class VoiceStateMachine:
    """
    Thread-safe voice state machine.
    All public methods are safe to call from both sync and async contexts.
    """

    MAX_QUEUE_SIZE = 3

    def __init__(self):
        self._state = VoiceState.IDLE
        self._lock = asyncio.Lock()

        # Cancellation token for the active LLM request
        self._llm_cancel_event: Optional[asyncio.Event] = None

        # Ring buffer — last 1000 request metrics
        self._metrics: deque[RequestMetric] = deque(maxlen=1000)
        self._current_metric: Optional[RequestMetric] = None

        # Audio command queue (passive buffer — rejection logic lives HERE)
        self._audio_queue: asyncio.Queue = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)

        # Session timeout task (Continuous Session mode)
        self._session_timeout_task: Optional[asyncio.Task] = None
        self._session_timeout_seconds: float = 30.0

        # Callback hooks (set by VoiceEngine after construction)
        self.on_state_change = None          # async callable(new_state)
        self.on_queue_full_notify = None     # async callable()  — plays "busy" audio

        logger.info("[VoiceStateMachine] Initialized in IDLE state.")

    # ── State Transitions ───────────────────────────────────────────────────────

    @property
    def state(self) -> VoiceState:
        return self._state

    async def transition(self, new_state: VoiceState) -> bool:
        """
        Attempt a state transition.  Returns True on success, False if blocked.
        Thread-safe via asyncio.Lock.
        """
        async with self._lock:
            allowed = _TRANSITIONS.get(self._state, set())
            if new_state not in allowed:
                logger.warning(
                    f"[VoiceStateMachine] BLOCKED illegal transition: "
                    f"{self._state.name} → {new_state.name}"
                )
                return False

            old = self._state
            self._state = new_state
            logger.info(f"[VoiceStateMachine] {old.name} → {new_state.name}")

            # Side effects per transition
            if new_state == VoiceState.THINKING:
                self._llm_cancel_event = asyncio.Event()
                self._current_metric = RequestMetric()

            if new_state in (VoiceState.IDLE, VoiceState.LISTENING):
                self._cancel_session_timeout()

            if self.on_state_change:
                asyncio.ensure_future(self.on_state_change(new_state))

            return True

    # ── Audio Queue (with State Machine owning rejection) ───────────────────────

    async def enqueue_audio(self, audio_path: str) -> bool:
        """
        Enqueue a captured audio path for transcription.
        If the queue is full, THIS method (State Machine) rejects and notifies.
        Returns True if enqueued, False if rejected.
        """
        if self._audio_queue.full():
            logger.warning("[VoiceStateMachine] Audio queue full — rejecting command.")
            if self.on_queue_full_notify:
                asyncio.ensure_future(self.on_queue_full_notify())
            return False
        await self._audio_queue.put(audio_path)
        return True

    async def dequeue_audio(self) -> str:
        """Block until an audio path is available."""
        return await self._audio_queue.get()

    # ── LLM Cancellation ────────────────────────────────────────────────────────

    def get_llm_cancel_event(self) -> Optional[asyncio.Event]:
        return self._llm_cancel_event

    async def cancel_llm(self):
        """Signal the active LLM request to cancel."""
        if self._llm_cancel_event:
            logger.info("[VoiceStateMachine] Cancelling active LLM request.")
            self._llm_cancel_event.set()

    # ── Session Timeout (Continuous Session mode) ────────────────────────────────

    def start_session_timeout(self):
        """Start the 30-second continuous session countdown."""
        self._cancel_session_timeout()
        self._session_timeout_task = asyncio.ensure_future(self._session_timeout_coro())

    def _cancel_session_timeout(self):
        if self._session_timeout_task and not self._session_timeout_task.done():
            self._session_timeout_task.cancel()
            self._session_timeout_task = None

    async def _session_timeout_coro(self):
        await asyncio.sleep(self._session_timeout_seconds)
        # Only fire from safe states — never cut off mid-utterance
        safe_states = {VoiceState.IDLE, VoiceState.LISTENING}
        if self._state in safe_states:
            logger.info("[VoiceStateMachine] Session timeout — returning to IDLE.")
            await self.transition(VoiceState.IDLE)
        else:
            logger.info(
                f"[VoiceStateMachine] Session timeout deferred "
                f"(state={self._state.name})"
            )

    # ── Latency Metrics ──────────────────────────────────────────────────────────

    def record_vad(self, ms: float):
        if self._current_metric:
            self._current_metric.vad_ms = ms

    def record_stt(self, ms: float):
        if self._current_metric:
            self._current_metric.stt_ms = ms

    def record_llm(self, ms: float):
        if self._current_metric:
            self._current_metric.llm_ms = ms

    def record_tts(self, ms: float):
        if self._current_metric:
            self._current_metric.tts_ms = ms

    def finalize_metric(self):
        if self._current_metric:
            m = self._current_metric
            m.e2e_ms = m.vad_ms + m.stt_ms + m.llm_ms + m.tts_ms
            logger.info(
                f"[Metrics] VAD={m.vad_ms:.0f}ms STT={m.stt_ms:.0f}ms "
                f"LLM={m.llm_ms:.0f}ms TTS={m.tts_ms:.0f}ms "
                f"E2E={m.e2e_ms:.0f}ms"
            )
            self._metrics.append(m)
            self._current_metric = None

    def get_stats(self) -> dict:
        """Returns data for the /voice/stats endpoint."""
        metrics = list(self._metrics)
        if not metrics:
            return {"state": self._state.name, "total_requests": 0}
        avg = lambda key: sum(getattr(m, key) for m in metrics) / len(metrics)
        return {
            "state":          self._state.name,
            "total_requests": len(metrics),
            "avg_vad_ms":     round(avg("vad_ms"), 1),
            "avg_stt_ms":     round(avg("stt_ms"), 1),
            "avg_llm_ms":     round(avg("llm_ms"), 1),
            "avg_tts_ms":     round(avg("tts_ms"), 1),
            "avg_e2e_ms":     round(avg("e2e_ms"), 1),
            "last_10":        [m.to_dict() for m in list(metrics)[-10:]],
        }


# ── Singleton ───────────────────────────────────────────────────────────────────
voice_state_machine = VoiceStateMachine()
