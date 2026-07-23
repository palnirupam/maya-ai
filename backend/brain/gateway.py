"""
Channel Gateway
===============
A single, reusable "turn runner" that every channel (Telegram, WhatsApp,
WebSocket UI, desktop voice, and future ones like Discord/Slack) uses to talk to
the brain.

Why this exists
---------------
Each channel previously re-implemented the same consume loop around
``orchestrator.process_user_input_stream``:
  * accumulate streamed text chunks
  * strip leaked model chain-of-thought (only Telegram did this — voice/UI leaked)
  * pull out special control tokens (MODE_CHANGE_TRIGGERED / SYSTEM_STATE_TRIGGERED)
  * forward structured events (approval requests, agent status, reasoning)

Centralising it here means:
  * adding a new channel is ~30 lines (implement on_event + send), and
  * every channel gets identical, clean output and control-token handling.

The channel-specific rendering (Telegram buttons vs. websocket events vs. spoken
sentences) stays in the channel via the ``on_text`` / ``on_event`` callbacks.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from .orchestrator import orchestrator
from .providers.gemini_adapter import ThinkStripper

logger = logging.getLogger(__name__)

# Control tokens the brain may embed in the text stream.
MODE_CHANGE_TOKEN = "MODE_CHANGE_TRIGGERED:"
SYSTEM_STATE_TOKEN = "SYSTEM_STATE_TRIGGERED:"

DEFAULT_TURN_TIMEOUT = 120.0

# on_text(chunk: str)  -> live, tag-stripped text for channels that stream.
# on_event(event: dict) -> structured events (tool_call_request, agent_status, ...).
# should_stop()         -> True to abort consuming mid-stream (e.g. voice barge-in).
TextCb = Callable[[str], Optional[Awaitable[None]]]
EventCb = Callable[[dict], Optional[Awaitable[None]]]
StopCb = Callable[[], bool]


@dataclass
class TurnResult:
    """Everything a channel needs after one user turn."""
    final_text: str = ""          # cleaned, control tokens removed — safe to show/speak
    raw_text: str = ""            # accumulated text before cleaning (for logging)
    mode_change: Optional[str] = None    # target mode if MODE_CHANGE_TRIGGERED was seen
    system_state: Optional[str] = None   # action if SYSTEM_STATE_TRIGGERED was seen
    events: list[dict] = field(default_factory=list)  # all dict events seen
    timed_out: bool = False
    stopped: bool = False         # should_stop() aborted the stream (e.g. barge-in)


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        await value


def _extract_token(text: str, token: str) -> Optional[str]:
    """Return the first whitespace-delimited word after `token`, or None."""
    if token not in text:
        return None
    try:
        return text.split(token, 1)[1].strip().split()[0]
    except IndexError:
        return None


async def run_turn(
    session_id: str,
    text: str,
    *,
    image_base64: Optional[str] = None,
    on_text: Optional[TextCb] = None,
    on_event: Optional[EventCb] = None,
    should_stop: Optional[StopCb] = None,
    timeout: Optional[float] = DEFAULT_TURN_TIMEOUT,
) -> TurnResult:
    """Run one user turn through the brain and return a normalized TurnResult.

    - String chunks are accumulated; a streaming ThinkStripper feeds `on_text`
      live (tags removed across chunk boundaries), and the full accumulated text
      is cleaned once more with clean_full() for `final_text`.
    - Dict chunks are collected in `events` and forwarded to `on_event`.
    - MODE_CHANGE_TRIGGERED / SYSTEM_STATE_TRIGGERED tokens are detected.
    - `should_stop` is polled before each chunk; if it returns True the stream is
      aborted (result.stopped=True) and the held-back stripper tail is discarded
      so no further text/audio is emitted after a barge-in.
    - `timeout=None` disables the turn timeout (for unbounded real-time streams).
    """
    result = TurnResult()
    stripper = ThinkStripper()

    async def _consume() -> None:
        async for chunk in orchestrator.process_user_input_stream(
            session_id, text, image_base64
        ):
            if should_stop is not None and should_stop():
                result.stopped = True
                break

            if isinstance(chunk, dict):
                result.events.append(chunk)
                if on_event is not None:
                    await _maybe_await(on_event(chunk))
                continue

            # Text chunk.
            result.raw_text += chunk
            if on_text is not None:
                visible = stripper.feed(chunk)
                if visible:
                    await _maybe_await(on_text(visible))

    try:
        await asyncio.wait_for(_consume(), timeout=timeout)
    except asyncio.TimeoutError:
        result.timed_out = True
        logger.warning("run_turn timed out for session=%s text=%r", session_id, text[:80])

    # Flush any tail held by the streaming stripper — unless the turn was
    # aborted mid-stream, in which case we must not emit more text/audio.
    if on_text is not None and not result.stopped:
        tail = stripper.flush()
        if tail:
            await _maybe_await(on_text(tail))

    # Authoritative clean of the whole message (handles plain-text CoT leaks).
    result.final_text = ThinkStripper.clean_full(result.raw_text).strip()
    result.mode_change = _extract_token(result.raw_text, MODE_CHANGE_TOKEN)
    result.system_state = _extract_token(result.raw_text, SYSTEM_STATE_TOKEN)

    # Never surface the raw control tokens to the user.
    for tok in (MODE_CHANGE_TOKEN, SYSTEM_STATE_TOKEN):
        if tok in result.final_text:
            result.final_text = result.final_text.split(tok, 1)[0].strip()

    return result
