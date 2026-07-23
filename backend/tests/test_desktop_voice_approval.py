from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.voice.desktop_voice_engine import (
    _forward_desktop_gateway_event,
    _is_control_token_stream,
)


@pytest.mark.asyncio
async def test_native_voice_forwards_approval_to_connected_ui() -> None:
    request = {"request_id": "req-1", "tool_name": "pc", "payload": {}}
    manager = MagicMock()
    manager.active_connections = [object()]
    manager.broadcast_event = AsyncMock()

    with patch("backend.api.websocket.manager.manager", manager):
        await _forward_desktop_gateway_event(
            {"type": "tool_call_request", "data": request}
        )

    manager.broadcast_event.assert_awaited_once_with(
        "tool_approval_request", request
    )


@pytest.mark.asyncio
async def test_native_voice_denies_approval_when_ui_is_unavailable() -> None:
    manager = MagicMock()
    manager.active_connections = []
    manager.broadcast_event = AsyncMock()
    planner = MagicMock()
    planner.resolve_tool.return_value = {"status": "denied"}

    with (
        patch("backend.api.websocket.manager.manager", manager),
        patch("backend.brain.reasoning.tool_planner.tool_planner", planner),
    ):
        await _forward_desktop_gateway_event(
            {
                "type": "tool_call_request",
                "data": {"request_id": "req-2", "tool_name": "pc", "payload": {}},
            }
        )

    manager.broadcast_event.assert_not_awaited()
    planner.resolve_tool.assert_called_once_with(
        "req-2",
        approved=False,
        user_id="desktop_voice_no_ui",
    )


@pytest.mark.asyncio
async def test_native_voice_ignores_non_approval_events() -> None:
    with patch("backend.api.websocket.manager.manager") as manager:
        await _forward_desktop_gateway_event(
            {"type": "agent_status", "data": {"status": "thinking"}}
        )

    manager.broadcast_event.assert_not_called()


@pytest.mark.parametrize(
    "text",
    [
        "SYSTEM_STATE_TRIGGERED:shutdown",
        "  MODE_CHANGE_TRIGGERED:coding",
        "\nSYSTEM_STATE_TRIGGERED:sleep",
    ],
)
def test_leading_control_token_is_never_spoken(text: str) -> None:
    # Regression (R07): the desktop voice engine used to speak
    # "SYSTEM_STATE_TRIGGERED:shutdown" aloud because its on_text handler only
    # stripped ```macro blocks, unlike the WebSocket handler which suppresses
    # these internal signals before TTS.
    assert _is_control_token_stream(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Thik ache, shutdown korchi.",
        "Ami tomake SYSTEM_STATE_TRIGGERED bujhte bollam na",  # quoted mid-reply
        "coding mode e gelam",
        "",
    ],
)
def test_normal_reply_is_spoken(text: str) -> None:
    # A real answer that merely mentions the phrase later must still be spoken.
    assert _is_control_token_stream(text) is False
