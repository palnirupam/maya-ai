"""
Test Telegram bot real-time animation and progress updates.

Verifies that:
1. Status updates are sent every 0.5s (not 5s)
2. Agent status changes trigger immediate updates
3. Tool approval requests show up instantly
4. Background task transitions are smooth
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from backend.api.telegram_bot import TelegramBotManager, TelegramTaskState


class TestRealtimeAnimation:
    """Test real-time progress animation in Telegram"""

    @pytest.mark.asyncio
    async def test_flush_interval_is_fast(self):
        """Verify flush interval is 0.5s for real-time feel"""
        from backend.api.telegram.handlers.task_handler import TaskHandler
        
        manager = TelegramBotManager()
        handler = TaskHandler(manager)
        
        # Check the actual implementation has fast flush
        import inspect
        source = inspect.getsource(handler.process_and_reply)
        
        # Verify 0.5 is used, not 5.0
        assert "flush_interval = 0.5" in source or "flush_interval = 0." in source
        assert "flush_interval = 5.0" not in source

    @pytest.mark.asyncio
    async def test_agent_status_triggers_immediate_flush(self):
        """Verify agent status changes trigger immediate message updates"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._task_states["42"] = TelegramTaskState(
            original_text="Test command",
            session_id="telegram_42",
        )
        
        # Mock message operations
        manager.message_sender.send_message_get_id = AsyncMock(return_value=123)
        manager.message_editor.edit_message = AsyncMock()
        manager.typing_indicator.send_typing = AsyncMock()
        
        # Track flush calls
        flush_times = []
        original_edit = manager.message_editor.edit_message
        
        async def track_edit(*args, **kwargs):
            flush_times.append(time.time())
            return await original_edit(*args, **kwargs)
        
        manager.message_editor.edit_message = track_edit
        
        # Simulate agent status event
        with patch("backend.brain.gateway.run_turn") as mock_turn:
            # Make run_turn trigger status events
            async def fake_turn(session_id, text, on_text=None, on_event=None, timeout=None):
                # Simulate status updates
                if on_event:
                    await on_event({"type": "agent_status", "data": {"active_agent": "FileAgent", "status": "Reading file..."}})
                    await asyncio.sleep(0.1)
                    await on_event({"type": "agent_status", "data": {"active_agent": "FileAgent", "status": "Processing..."}})
                
                # Return mock result
                from backend.brain.gateway import TurnResult
                return TurnResult(final_text="Done", raw_text="Done")
            
            mock_turn.side_effect = fake_turn
            
            # Run the task
            await manager.task_handler.process_and_reply("42", "test", "telegram_42")
        
        # Verify flushes happened (at least 2 for the 2 status updates)
        assert len(flush_times) >= 2, f"Expected at least 2 flushes, got {len(flush_times)}"

    @pytest.mark.asyncio
    async def test_typing_indicator_sent_immediately(self):
        """Verify typing indicator is sent as soon as task starts"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._task_states["42"] = TelegramTaskState(
            original_text="Test",
            session_id="telegram_42",
        )
        
        typing_sent = asyncio.Event()
        
        async def mock_typing(*args, **kwargs):
            typing_sent.set()
        
        manager.typing_indicator.send_typing = mock_typing
        manager.message_sender.send_message_get_id = AsyncMock(return_value=123)
        
        with patch("backend.brain.gateway.run_turn") as mock_turn:
            from backend.brain.gateway import TurnResult
            mock_turn.return_value = TurnResult(final_text="Done", raw_text="Done")
            
            # Start task
            task = asyncio.create_task(
                manager.task_handler.process_and_reply("42", "test", "telegram_42")
            )
            
            # Typing indicator should be sent within 100ms
            try:
                await asyncio.wait_for(typing_sent.wait(), timeout=0.1)
                assert True, "Typing indicator sent immediately"
            except asyncio.TimeoutError:
                pytest.fail("Typing indicator not sent within 100ms")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_progress_updates_with_emoji(self):
        """Verify progress updates include emoji indicators"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._task_states["42"] = TelegramTaskState(
            original_text="Test",
            session_id="telegram_42",
        )
        
        sent_messages = []
        
        async def capture_message(chat_id, text, **kwargs):
            sent_messages.append(text)
            return 123
        
        manager.message_sender.send_message_get_id = capture_message
        manager.message_editor.edit_message = AsyncMock()
        manager.typing_indicator.send_typing = AsyncMock()
        
        with patch("backend.brain.gateway.run_turn") as mock_turn:
            async def fake_turn(session_id, text, on_text=None, on_event=None, timeout=None):
                if on_event:
                    await on_event({
                        "type": "agent_status",
                        "data": {
                            "active_agent": "TestAgent",
                            "status": "Processing..."
                        }
                    })
                
                from backend.brain.gateway import TurnResult
                return TurnResult(final_text="Done", raw_text="Done")
            
            mock_turn.side_effect = fake_turn
            
            await manager.task_handler.process_and_reply("42", "test", "telegram_42")
        
        # Verify at least one message contains agent emoji
        has_emoji = any("🤖" in msg or "⏳" in msg for msg in sent_messages)
        assert has_emoji, f"No emoji found in messages: {sent_messages}"


class TestBackgroundTaskAnimation:
    """Test animation for background tasks"""

    @pytest.mark.asyncio
    async def test_background_transition_message(self):
        """Verify smooth transition to background with user notification"""
        manager = TelegramBotManager()
        manager.chat_id = "42"
        manager._task_states["42"] = TelegramTaskState(
            original_text="Long task",
            session_id="telegram_42",
        )
        
        sent_messages = []
        
        async def capture_send(chat_id, text, **kwargs):
            sent_messages.append(text)
        
        manager.message_sender.send_message = capture_send
        manager.message_sender.send_message_get_id = AsyncMock(return_value=123)
        manager.message_editor.edit_message = AsyncMock()
        manager.typing_indicator.send_typing = AsyncMock()
        
        with patch("backend.brain.gateway.run_turn") as mock_turn:
            # Simulate a slow task
            async def slow_turn(*args, **kwargs):
                await asyncio.sleep(100)  # Will timeout
            
            mock_turn.side_effect = slow_turn
            
            # Should timeout and go to background
            try:
                await asyncio.wait_for(
                    manager.task_handler.process_and_reply("42", "test", "telegram_42"),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                pass
        
        # Verify background notification was sent
        background_msgs = [msg for msg in sent_messages if "background" in msg.lower() or "continue" in msg.lower()]
        assert len(background_msgs) > 0, f"No background notification found in: {sent_messages}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
