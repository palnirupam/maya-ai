import re
from unittest.mock import AsyncMock, patch

import pytest

from backend.api.telegram_bot import PendingWAReply, TelegramBotManager
from backend.brain.language_style import (
    BANGLISH,
    ENGLISH,
    HINDILISH,
    set_latest_conversation_style,
)


@pytest.fixture(autouse=True)
def reset_latest_conversation_style():
    set_latest_conversation_style(ENGLISH)
    yield
    set_latest_conversation_style(ENGLISH)


@pytest.mark.asyncio
async def test_callback_from_unauthorized_chat_is_ignored():
    manager = TelegramBotManager()
    manager.chat_id = "42"
    manager._answer_callback = AsyncMock()
    manager._wa_cb_allow = AsyncMock()

    await manager._handle_callback_query(
        {
            "id": "callback-1",
            "data": "wa_allow_wa-1",
            "from": {"id": 7},
            "message": {"chat": {"id": 7}},
        }
    )

    manager._answer_callback.assert_awaited_once_with("callback-1")
    manager._wa_cb_allow.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_from_wrong_private_actor_is_ignored():
    manager = TelegramBotManager()
    manager.chat_id = "42"
    manager._answer_callback = AsyncMock()
    manager._wa_cb_allow = AsyncMock()

    await manager._handle_callback_query(
        {
            "id": "callback-2",
            "data": "wa_allow_wa-1",
            "from": {"id": 7},
            "message": {"chat": {"id": 42}},
        }
    )

    manager._answer_callback.assert_awaited_once_with("callback-2")
    manager._wa_cb_allow.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["Yes", "হ্যাঁ", "জি"])
async def test_typed_yes_resolves_pending_tool_approval(answer):
    manager = TelegramBotManager()
    manager.chat_id = "42"
    manager._pending_exec_approval["42"] = "req-power"
    manager._send_message = AsyncMock()

    with patch("backend.api.telegram_bot.tool_planner.resolve_tool") as resolve:
        await manager._handle_message({"chat": {"id": 42}, "text": answer})

    resolve.assert_called_once_with(
        "req-power",
        approved=True,
        user_id="telegram:42",
    )
    assert "42" not in manager._pending_exec_approval


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["No", "না", "cancel"])
async def test_typed_no_denies_pending_tool_approval(answer):
    manager = TelegramBotManager()
    manager.chat_id = "42"
    manager._pending_exec_approval["42"] = "req-power"
    manager._send_message = AsyncMock()

    with patch("backend.api.telegram_bot.tool_planner.resolve_tool") as resolve:
        await manager._handle_message({"chat": {"id": 42}, "text": answer})

    resolve.assert_called_once_with(
        "req-power",
        approved=False,
        user_id="telegram:42",
    )
    assert "42" not in manager._pending_exec_approval


@pytest.mark.asyncio
async def test_whatsapp_allow_failure_does_not_authorize_sender():
    manager = TelegramBotManager()
    manager._send_message = AsyncMock()
    manager._remember_chat_language_style("42", "ami Banglish e kotha bolchi")
    pending = PendingWAReply(
        id="wa-1",
        chat_id_wa="919876543210@c.us",
        from_number="919876543210",
        from_name="Unknown",
        is_group=False,
        group_name="",
        trigger_msg="hello",
        context_messages=[],
        is_known=False,
    )
    manager._pending_wa[pending.id] = pending

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager."
        "whatsapp_manager.register_known_sender",
        return_value=False,
    ):
        await manager._wa_cb_allow("42", pending.id)

    assert pending.is_known is False
    sent_text = manager._send_message.call_args.args[1]
    assert "allow kora gelo na" in sent_text
    set_latest_conversation_style(ENGLISH)


def test_unknown_whatsapp_sender_has_no_reply_controls_before_allow():
    manager = TelegramBotManager()
    pending = PendingWAReply(
        id="wa-unknown",
        chat_id_wa="919876543210@c.us",
        from_number="919876543210",
        from_name="Unknown",
        is_group=False,
        group_name="",
        trigger_msg="hello",
        context_messages=[],
        is_known=False,
    )

    _, markup = manager._build_wa_notification(pending)
    callbacks = {
        button["callback_data"]
        for row in markup["inline_keyboard"]
        for button in row
    }
    assert callbacks == {
        "wa_allow_wa-unknown",
        "wa_block_wa-unknown",
        "wa_ignore_wa-unknown",
    }


@pytest.mark.parametrize(
    ("style", "header", "manual_button"),
    [
        (ENGLISH, "New WhatsApp message!", "Write reply"),
        (BANGLISH, "Notun WhatsApp message!", "Nije likhi"),
        (HINDILISH, "Naya WhatsApp message!", "Khud likhu"),
    ],
)
def test_whatsapp_notification_follows_telegram_chat_style(
    style, header, manual_button
):
    manager = TelegramBotManager()
    pending = PendingWAReply(
        id=f"wa-{style}",
        chat_id_wa="919876543210@c.us",
        from_number="919876543210",
        from_name="Known Sender",
        is_group=False,
        group_name="",
        trigger_msg="Original WhatsApp message",
        context_messages=[],
        is_known=True,
    )

    text, markup = manager._build_wa_notification(pending, style)
    button_text = " ".join(
        button["text"]
        for row in markup["inline_keyboard"]
        for button in row
    )

    assert header in text
    assert manual_button in button_text
    assert "Original WhatsApp message" in text
    assert not re.search(r"[\u0900-\u097f\u0980-\u09ff]", text + button_text)


def test_telegram_chat_language_style_tracks_switches_and_short_followups():
    manager = TelegramBotManager()

    try:
        assert manager._remember_chat_language_style(
            "42", "ami ekhon Banglish e kotha bolchi"
        ) == BANGLISH
        assert manager._remember_chat_language_style("42", "ok") == BANGLISH
        assert manager._remember_chat_language_style(
            "42", "Please show me the latest task status"
        ) == ENGLISH
        assert manager._remember_chat_language_style(
            "42", "mujhe abhi status batao"
        ) == HINDILISH
    finally:
        set_latest_conversation_style(ENGLISH)


@pytest.mark.asyncio
async def test_incoming_whatsapp_notification_uses_latest_maya_style():
    manager = TelegramBotManager()
    manager.chat_id = "42"
    manager._send_message = AsyncMock()

    try:
        set_latest_conversation_style(HINDILISH)
        await manager._handle_whatsapp_incoming(
            {
                "id": "wa-incoming",
                "chatId": "919876543210@c.us",
                "fromNumber": "919876543210",
                "fromName": "Known Sender",
                "isGroup": False,
                "groupName": "",
                "triggerMsg": "hello",
                "contextMessages": [],
                "isKnown": True,
            }
        )
    finally:
        set_latest_conversation_style(ENGLISH)

    sent_text = manager._send_message.call_args.args[1]
    markup = manager._send_message.call_args.kwargs["reply_markup"]
    assert "Naya WhatsApp message!" in sent_text
    assert any(
        "Khud likhu" in button["text"]
        for row in markup["inline_keyboard"]
        for button in row
    )


@pytest.mark.asyncio
async def test_unknown_whatsapp_sender_cannot_use_forged_reply_callbacks():
    manager = TelegramBotManager()
    manager._send_message = AsyncMock()
    pending = PendingWAReply(
        id="wa-forged",
        chat_id_wa="919876543210@c.us",
        from_number="919876543210",
        from_name="Unknown",
        is_group=False,
        group_name="",
        trigger_msg="hello",
        context_messages=[],
        is_known=False,
        gemini_draft="draft",
    )
    manager._pending_wa[pending.id] = pending

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager."
        "whatsapp_manager.reply_to_chat"
    ) as reply_to_chat:
        await manager._wa_cb_gemini("42", pending.id)
        await manager._wa_cb_send_draft("42", pending.id)
        await manager._wa_cb_manual("42", pending.id)
        await manager._send_wa_reply("42", pending, "forged reply")

    assert manager._wa_manual_awaiting == {}
    reply_to_chat.assert_not_called()
    assert manager._send_message.await_count == 4


@pytest.mark.asyncio
async def test_unknown_sender_manual_text_does_not_consume_pending_reply():
    manager = TelegramBotManager()
    manager._send_message = AsyncMock()
    pending = PendingWAReply(
        id="wa-manual-forged",
        chat_id_wa="919876543210@c.us",
        from_number="919876543210",
        from_name="Unknown",
        is_group=False,
        group_name="",
        trigger_msg="hello",
        context_messages=[],
        is_known=False,
    )
    manager._pending_wa[pending.id] = pending
    manager._wa_manual_awaiting["42"] = pending.id

    await manager._complete_manual_wa_reply("42", pending.id, "forged reply")

    assert manager._pending_wa[pending.id] is pending
    assert "42" not in manager._wa_manual_awaiting


@pytest.mark.asyncio
async def test_whatsapp_block_failure_keeps_pending_sender():
    manager = TelegramBotManager()
    manager._send_message = AsyncMock()
    manager._remember_chat_language_style("42", "ami Banglish e kotha bolchi")
    pending = PendingWAReply(
        id="wa-block",
        chat_id_wa="919876543210@c.us",
        from_number="919876543210",
        from_name="Unknown",
        is_group=False,
        group_name="",
        trigger_msg="hello",
        context_messages=[],
        is_known=False,
    )
    manager._pending_wa[pending.id] = pending

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager."
        "whatsapp_manager.block_sender",
        return_value=False,
    ):
        await manager._wa_cb_block("42", pending.id)

    assert pending.id in manager._pending_wa
    sent_text = manager._send_message.call_args.args[1]
    assert "block kora gelo na" in sent_text
    set_latest_conversation_style(ENGLISH)


@pytest.mark.asyncio
async def test_legacy_shutdown_confirmation_uses_unified_pc_result():
    manager = TelegramBotManager()
    manager._pending_dangerous["42"] = __import__(
        "backend.api.telegram_bot", fromlist=["PendingDangerousCmd"]
    ).PendingDangerousCmd(telegram_chat_id="42", original_text="shutdown")
    manager._send_message = AsyncMock()

    with patch("backend.tools.unified.pc", return_value="ERR: Access denied") as pc:
        await manager._cb_confirm_shutdown("42")

    pc.assert_called_once_with(action="shutdown")
    sent_text = manager._send_message.call_args.args[1]
    assert "execute করা যায়নি" in sent_text
    assert "৫ সেকেন্ডের মধ্যে PC বন্ধ হবে" not in sent_text
