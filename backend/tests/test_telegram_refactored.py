"""
Comprehensive integration tests for refactored Telegram bot.

Tests the new modular structure:
- Config module
- State models
- Message handling
- Callback handling  
- Task processing
- WhatsApp integration
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.api.telegram_bot import (
    TelegramBotManager,
    PendingWAReply,
    TelegramTaskState,
    APPROVAL_YES,
    APPROVAL_NO,
)


class TestModularStructure:
    """Test that the modular structure is properly set up"""

    def test_manager_has_all_submodules(self):
        """Verify manager has all required sub-managers"""
        manager = TelegramBotManager()
        
        # Core modules
        assert hasattr(manager, 'lifecycle')
        assert hasattr(manager, 'polling')
        
        # Messaging modules
        assert hasattr(manager, 'message_sender')
        assert hasattr(manager, 'message_editor')
        assert hasattr(manager, 'typing_indicator')
        
        # Handler modules
        assert hasattr(manager, 'message_handler')
        assert hasattr(manager, 'callback_handler')
        assert hasattr(manager, 'command_handler')
        assert hasattr(manager, 'task_handler')
        
        # WhatsApp module
        assert hasattr(manager, 'whatsapp')

    def test_backward_compatibility_properties(self):
        """Verify backward compatibility properties work"""
        manager = TelegramBotManager()
        
        # messaging -> message_sender
        assert manager.messaging is manager.message_sender
        
        # typing -> typing_indicator
        assert manager.typing is manager.typing_indicator
        
        # utils stub
        assert hasattr(manager, 'utils')
        assert hasattr(manager.utils, 'default_keyboard')


class TestMessageHandling:
    """Test message handling and routing"""

    @pytest.mark.asyncio
    async def test_tool_approval_yes(self):
        """Test tool approval with 'yes' response"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._pending_exec_approval["42"] = "req-test-123"
        manager._send_message = AsyncMock()
        
        with patch("backend.brain.reasoning.tool_planner.tool_planner") as mock_planner:
            mock_planner.resolve_tool = MagicMock()
            
            # Simulate user saying "yes"
            message = {"chat": {"id": 42}, "text": "yes"}
            await manager.message_handler.handle_message(message)
            
            # Verify tool was approved
            mock_planner.resolve_tool.assert_called_once_with(
                "req-test-123",
                approved=True,
                user_id="telegram:42",
            )
            
            # Verify approval was removed
            assert "42" not in manager._pending_exec_approval

    @pytest.mark.asyncio
    async def test_tool_approval_no(self):
        """Test tool approval with 'no' response"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._pending_exec_approval["42"] = "req-test-456"
        manager._send_message = AsyncMock()
        
        with patch("backend.brain.reasoning.tool_planner.tool_planner") as mock_planner:
            mock_planner.resolve_tool = MagicMock()
            
            # Simulate user saying "no"
            message = {"chat": {"id": 42}, "text": "no"}
            await manager.message_handler.handle_message(message)
            
            # Verify tool was denied
            mock_planner.resolve_tool.assert_called_once_with(
                "req-test-456",
                approved=False,
                user_id="telegram:42",
            )
            
            # Verify approval was removed
            assert "42" not in manager._pending_exec_approval

    @pytest.mark.asyncio
    async def test_pairing_with_correct_code(self):
        """Test pairing with correct code"""
        manager = TelegramBotManager()
        manager.pairing_code = "MAYA123"
        manager._send_message = AsyncMock()
        
        message = {"chat": {"id": 99}, "text": "/pair MAYA123"}
        
        with patch("backend.database.connection.SessionLocal"):
            await manager.message_handler.handle_message(message)
        
        # Verify chat was paired
        assert manager.chat_id == "99"
        manager._send_message.assert_called()

    @pytest.mark.asyncio
    async def test_pairing_with_wrong_code(self):
        """Test pairing with wrong code"""
        manager = TelegramBotManager()
        manager.pairing_code = "MAYA123"
        manager._send_message = AsyncMock()
        
        message = {"chat": {"id": 99}, "text": "/pair WRONG"}
        await manager.message_handler.handle_message(message)
        
        # Verify chat was NOT paired
        assert manager.chat_id is None
        
        # Verify error message was sent
        manager._send_message.assert_called_once()
        args = manager._send_message.call_args
        assert "Invalid" in args[0][1] or "❌" in args[0][1]


class TestWhatsAppIntegration:
    """Test WhatsApp notification handling"""

    def test_pending_wa_reply_creation(self):
        """Test PendingWAReply dataclass creation"""
        pending = PendingWAReply(
            id="wa-123",
            chat_id_wa="91234567890@c.us",
            from_number="919876543210",
            from_name="Test User",
            is_group=False,
            group_name="",
            trigger_msg="Hello Maya!",
            context_messages=[],
            is_known=True,
        )
        
        assert pending.id == "wa-123"
        assert pending.from_name == "Test User"
        assert pending.is_group is False
        assert pending.is_known is True

    @pytest.mark.asyncio
    async def test_whatsapp_notification_build(self):
        """Test WhatsApp notification message building"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        
        pending = PendingWAReply(
            id="wa-test",
            chat_id_wa="91234567890@c.us",
            from_number="919876543210",
            from_name="John Doe",
            is_group=False,
            group_name="",
            trigger_msg="Test message",
            context_messages=[],
            is_known=True,
        )
        
        text, markup = manager.whatsapp.build_wa_notification(pending, "english")
        
        # Verify notification contains key info
        assert "John Doe" in text
        assert "Test message" in text
        
        # Verify buttons exist
        assert "inline_keyboard" in markup
        assert len(markup["inline_keyboard"]) > 0


class TestTaskManagement:
    """Test task state management"""

    def test_task_state_creation(self):
        """Test TelegramTaskState dataclass creation"""
        state = TelegramTaskState(
            original_text="Test command",
            session_id="telegram_42",
        )
        
        assert state.original_text == "Test command"
        assert state.session_id == "telegram_42"
        assert state.state == "running"
        assert state.status == "Starting task..."
        assert state.backgrounded is False

    @pytest.mark.asyncio
    async def test_task_status_query(self):
        """Test task status query"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._send_message = AsyncMock()
        
        # Create a fake running task
        state = TelegramTaskState(
            original_text="Process file",
            session_id="telegram_42",
        )
        state.status = "Processing..."
        manager._task_states["42"] = state
        
        # Query status
        await manager._send_task_status("42")
        
        # Verify status was sent
        manager._send_message.assert_called_once()
        args = manager._send_message.call_args
        assert "Processing..." in args[0][1] or "running" in args[0][1].lower()


class TestCommandHandling:
    """Test command handling"""

    @pytest.mark.asyncio
    async def test_help_command(self):
        """Test /help command"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._send_message = AsyncMock()
        
        message = {"chat": {"id": 42}, "text": "/help"}
        await manager.message_handler.handle_message(message)
        
        # Verify help message was sent
        manager._send_message.assert_called_once()
        args = manager._send_message.call_args
        help_text = args[0][1]
        
        # Verify help contains key info
        assert "/help" in help_text or "Commands" in help_text or "help" in help_text.lower()

    @pytest.mark.asyncio
    async def test_status_command(self):
        """Test /status command"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._send_message = AsyncMock()
        
        message = {"chat": {"id": 42}, "text": "/status"}
        await manager.message_handler.handle_message(message)
        
        # Verify status message was sent
        manager._send_message.assert_called_once()
        args = manager._send_message.call_args
        status_text = args[0][1]
        
        # Verify status contains key info
        assert "Status" in status_text or "Bot" in status_text or "Active" in status_text


class TestConfigConstants:
    """Test configuration constants are properly exported"""

    def test_config_constants_exist(self):
        """Verify all config constants are accessible"""
        from backend.api.telegram_bot import (
            TELEGRAM_API,
            STREAM_TIMEOUT,
            BACKGROUND_TASK_TIMEOUT,
            APPROVAL_YES,
            APPROVAL_NO,
            SCREENSHOT_TRIGGER_KEYWORDS,
        )
        
        assert TELEGRAM_API == "https://api.telegram.org/bot{token}/{method}"
        assert STREAM_TIMEOUT == 60.0
        assert BACKGROUND_TASK_TIMEOUT == 900.0
        assert "yes" in APPROVAL_YES
        assert "no" in APPROVAL_NO
        assert len(SCREENSHOT_TRIGGER_KEYWORDS) > 0


class TestErrorHandling:
    """Test error handling and edge cases"""

    @pytest.mark.asyncio
    async def test_unauthorized_user_rejected(self):
        """Test that unauthorized users are rejected"""
        manager = TelegramBotManager()
        manager.chat_id = "42"  # Paired with chat 42
        manager._send_message = AsyncMock()
        
        # Different user tries to send message
        message = {"chat": {"id": 99}, "text": "Hello"}
        await manager.message_handler.handle_message(message)
        
        # Verify unauthorized message was sent
        manager._send_message.assert_called_once()
        args = manager._send_message.call_args
        assert args[0][0] == "99"  # Message sent to unauthorized user
        assert "Unauthorized" in args[0][1] or "❌" in args[0][1]

    @pytest.mark.asyncio
    async def test_empty_message_ignored(self):
        """Test that empty messages are ignored"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._send_message = AsyncMock()
        
        message = {"chat": {"id": 42}, "text": ""}
        await manager.message_handler.handle_message(message)
        
        # Verify no response was sent
        manager._send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_stop(self):
        """Test emergency stop functionality"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._send_message = AsyncMock()
        
        # Create a fake running task
        task = asyncio.create_task(asyncio.sleep(10))
        manager._active_tasks["42"] = task
        
        # Trigger emergency stop
        message = {"chat": {"id": 42}, "text": "stop"}
        await manager.message_handler.handle_message(message)
        
        # Verify task was cancelled
        await asyncio.sleep(0.1)  # Give time for cancellation
        assert task.cancelled() or task.done()
        
        # Verify stop message was sent
        manager._send_message.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
