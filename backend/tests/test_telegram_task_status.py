"""Regression tests for Telegram background-task status handling."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.api.telegram_bot import (
    TelegramBotManager,
    TelegramTaskState,
    _is_task_status_request,
)
from backend.brain.gateway import TurnResult


def test_task_status_phrase_detection_is_narrow():
    assert _is_task_status_request("status ki")
    assert _is_task_status_request("kaj ta ki holo?")
    assert _is_task_status_request("progress ki")
    assert not _is_task_status_request("battery status")
    assert not _is_task_status_request("new ta file delete koro")


@pytest.mark.asyncio
async def test_status_message_does_not_cancel_active_task():
    manager = TelegramBotManager()
    manager.chat_id = "42"
    manager._send_message = AsyncMock()

    release = asyncio.Event()

    async def _running_task():
        await release.wait()

    active = asyncio.create_task(_running_task())
    manager._active_tasks["42"] = active
    manager._task_states["42"] = TelegramTaskState(
        original_text="Create a PDF and email it",
        session_id="telegram_42",
        active_agent="Researcher",
        status="Searching the web...",
        backgrounded=True,
    )

    try:
        await manager._handle_message({"chat": {"id": 42}, "text": "status ki"})
        assert not active.cancelled()
        assert not active.done()
        sent_text = manager._send_message.await_args.args[1]
        assert "ekhono background-e cholche" in sent_text
        assert "Researcher: Searching the web" in sent_text
    finally:
        release.set()
        await active


@pytest.mark.asyncio
async def test_status_after_background_completion_is_not_a_new_task():
    manager = TelegramBotManager()
    manager.chat_id = "42"
    manager._send_message = AsyncMock()
    state = TelegramTaskState(
        original_text="Create a PDF and email it",
        session_id="telegram_42",
        state="completed",
        status="Completed.",
        backgrounded=True,
        final_text="PDF created and email sent.",
    )
    state.updated_at = state.started_at + 2
    manager._task_states["42"] = state

    await manager._handle_message({"chat": {"id": 42}, "text": "ki holo?"})

    assert "42" not in manager._active_tasks
    sent_text = manager._send_message.await_args.args[1]
    assert "complete hoyeche" in sent_text
    assert "already pathano hoyeche" in sent_text


@pytest.mark.asyncio
async def test_soft_timeout_keeps_turn_running_and_later_sends_result():
    manager = TelegramBotManager()
    manager._send_typing = AsyncMock()
    manager._send_message = AsyncMock()
    manager._send_message_get_id = AsyncMock(return_value=None)
    manager._edit_message = AsyncMock()
    manager._send_screenshot = AsyncMock()

    chat_id = "42"
    session_id = "telegram_42"
    state = TelegramTaskState(
        original_text="Create a PDF and email it",
        session_id=session_id,
    )
    manager._task_states[chat_id] = state

    started = asyncio.Event()
    release = asyncio.Event()
    cancelled = False

    async def _fake_run_turn(*args, on_event=None, **kwargs):
        nonlocal cancelled
        if on_event:
            await on_event({
                "type": "agent_status",
                "data": {
                    "active_agent": "Researcher",
                    "status": "Searching the web...",
                },
            })
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled = True
            raise
        return TurnResult(final_text="PDF created and email sent.")

    with (
        patch("backend.brain.gateway.run_turn", _fake_run_turn),
        patch("backend.api.telegram_bot.STREAM_TIMEOUT", 0.01),
        patch("backend.api.telegram_bot.BACKGROUND_TASK_TIMEOUT", 0.5),
    ):
        task = asyncio.create_task(
            manager._process_and_reply(chat_id, state.original_text, session_id)
        )
        manager._active_tasks[chat_id] = task
        await started.wait()
        await asyncio.sleep(0.03)

        assert not task.done()
        assert not cancelled
        assert state.backgrounded
        assert state.state == "running"

        await manager._send_task_status(chat_id)
        release.set()
        await task

    assert state.state == "completed"
    assert state.final_text == "PDF created and email sent."
    assert chat_id not in manager._active_tasks
    messages = [call.args[1] for call in manager._send_message.await_args_list]
    assert any("background-e" in message for message in messages)
    assert any("PDF created and email sent." in message for message in messages)


@pytest.mark.asyncio
async def test_old_task_cleanup_cannot_remove_new_task_mapping():
    manager = TelegramBotManager()
    manager._send_typing = AsyncMock()
    manager._send_message = AsyncMock()

    started = asyncio.Event()

    async def _fake_run_turn(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    chat_id = "42"
    session_id = "telegram_42"
    manager._task_states[chat_id] = TelegramTaskState("old", session_id)

    with patch("backend.brain.gateway.run_turn", _fake_run_turn):
        old_task = asyncio.create_task(
            manager._process_and_reply(chat_id, "old", session_id)
        )
        manager._active_tasks[chat_id] = old_task
        await started.wait()

        old_task.cancel()
        new_task = asyncio.create_task(asyncio.sleep(10))
        manager._active_tasks[chat_id] = new_task
        with pytest.raises(asyncio.CancelledError):
            await old_task

        assert manager._active_tasks[chat_id] is new_task
        new_task.cancel()
        await asyncio.gather(new_task, return_exceptions=True)
