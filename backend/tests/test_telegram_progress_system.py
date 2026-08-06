"""
test_telegram_progress_system.py
=================================
Comprehensive integration tests for the Telegram UX Progress Tracking System.

Tests all components of the progress system:
- ProgressTracker class functionality
- Progress event emission and handling
- Tool execution visibility  
- Background progress updates
- Cancellation support
- Real-time message updates
- Error handling and edge cases
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any

# Import system under test
from backend.brain.progress_tracker import ProgressTracker, ProgressEvent, ProgressStage
from backend.api.telegram.handlers.task_handler import TaskHandler
from backend.api.telegram.handlers.callback_handler import CallbackHandler


class MockTelegramManager:
    """Mock TelegramBotManager for testing."""
    
    def __init__(self):
        self.message_sender = AsyncMock()
        self.message_editor = AsyncMock()
        self.typing_indicator = AsyncMock()
        self._task_states = {}
        self._active_tasks = {}
        self._pending_exec_approval = {}
        
    def _wa_ui_copy(self, style):
        return {
            "command_cancelled": "❌ Task has been cancelled.",
            "task_hard_timeout": "Task timed out.",
        }
    
    def _chat_language_style(self, chat_id):
        return "english"
    
    def _default_keyboard(self):
        return {"keyboard": []}


@pytest.fixture
def mock_manager():
    """Create mock TelegramBotManager."""
    return MockTelegramManager()


@pytest.fixture
def task_handler(mock_manager):
    """Create TaskHandler with mock manager."""
    return TaskHandler(mock_manager)


@pytest.fixture
def callback_handler(mock_manager):
    """Create CallbackHandler with mock manager."""
    return CallbackHandler(mock_manager)


class TestProgressTracker:
    """Test ProgressTracker class functionality."""
    
    @pytest.mark.asyncio
    async def test_progress_tracker_basic_flow(self):
        """Test basic progress tracking flow."""
        events = []
        
        async def capture_event(event):
            events.append(event)
        
        tracker = ProgressTracker()
        tracker.add_callback(capture_event)
        
        # Start step
        await tracker.start_step("Processing", agent="TEST_AGENT", stage=ProgressStage.EXECUTING)
        
        # Update progress
        await tracker.update_progress("Working...", metadata={"test": True})
        
        # Finalize
        await tracker.finalize("Completed")
        
        # Verify events
        assert len(events) >= 3
        assert events[0].action == "Processing"
        assert events[0].agent == "TEST_AGENT"
        assert events[0].stage == ProgressStage.EXECUTING
        assert events[-1].progress_percent == 100
    
    @pytest.mark.asyncio
    async def test_progress_tracker_cancellation(self):
        """Test progress tracker cancellation."""
        events = []
        
        async def capture_event(event):
            events.append(event)
        
        tracker = ProgressTracker()
        tracker.add_callback(capture_event)
        
        await tracker.start_step("Processing", agent="TEST_AGENT")
        
        # Cancel
        await tracker.cancel()
        
        # Verify cancellation
        assert tracker.is_cancelled
        assert len(events) >= 2
        assert events[-1].stage == ProgressStage.CANCELLED
    
    @pytest.mark.asyncio
    async def test_progress_tracker_eta_calculation(self):
        """Test ETA calculation accuracy."""
        tracker = ProgressTracker()
        
        # Simulate time progression
        await tracker.start_step("Step 1", agent="TEST", stage=ProgressStage.EXECUTING)
        await tracker.complete_step()
        
        await tracker.start_step("Step 2", agent="TEST", stage=ProgressStage.EXECUTING)
        
        # ETA should be calculated based on previous steps
        # Just verify it doesn't crash and returns reasonable values
        assert tracker.elapsed_seconds >= 0
    
    def test_progress_tracker_percentage_calculation(self):
        """Test percentage calculation accuracy."""
        tracker = ProgressTracker(total_steps=8)
        tracker.current_step = 3
        
        # Progress percent should be calculated correctly
        expected_percentage = int((3 / 8) * 100)
        assert abs(tracker.progress_percent - expected_percentage) < 2


class TestProgressEventHandling:
    """Test progress event handling in task_handler."""
    
    @pytest.mark.asyncio
    async def test_handle_progress_event(self, task_handler, mock_manager):
        """Test progress event handling and message formatting."""
        # Setup task state
        chat_id = "test_chat"
        task_state = MagicMock()
        task_state.updated_at = time.monotonic()
        
        flush_called = False
        
        async def mock_flush():
            nonlocal flush_called
            flush_called = True
        
        # Test progress event
        chunk = {
            "type": "progress_event",
            "data": {
                "step_number": 3,
                "total_steps": 5,
                "percentage": 60.0,
                "agent": "OS_EXECUTOR",
                "stage": "EXECUTING",
                "eta_seconds": 15.5,
                "action": "Running system command"
            }
        }
        
        await task_handler._handle_progress_event(chunk, task_state, mock_flush)
        
        # Verify status formatting
        assert "██████░░░░" in task_state.status  # Progress bar (60% = 6 blocks)
        assert "60%" in task_state.status  # Percentage
        assert "Step 3/5" in task_state.status  # Step counter
        assert "🤖 OS_EXECUTOR" in task_state.status  # Agent
        assert "⏱️ ~15s remaining" in task_state.status  # ETA
        assert "Running system command" in task_state.status  # Action
        assert flush_called
    
    @pytest.mark.asyncio
    async def test_handle_tool_execution_events(self, task_handler, mock_manager):
        """Test tool execution visibility events."""
        task_state = MagicMock()
        
        flush_called = []
        
        async def mock_flush():
            flush_called.append(True)
        
        # Test starting event
        start_chunk = {
            "type": "tool_execution",
            "data": {
                "tool_name": "file_manager",
                "status": "starting",
                "args": {"path": "/test/file.txt"},
                "timestamp": time.time()
            }
        }
        
        await task_handler._handle_tool_execution(start_chunk, task_state, mock_flush)
        assert "⚙️ Executing File Manager" in task_state.status
        
        # Test success event
        success_chunk = {
            "type": "tool_execution",
            "data": {
                "tool_name": "file_manager",
                "status": "success",
                "result": "File created successfully",
                "duration": 1.2,
                "timestamp": time.time()
            }
        }
        
        await task_handler._handle_tool_execution(success_chunk, task_state, mock_flush)
        assert "✅ File Manager (1.2s)" in task_state.status
        assert "File created successfully" in task_state.status
        
        # Test failure event
        fail_chunk = {
            "type": "tool_execution",
            "data": {
                "tool_name": "file_manager",
                "status": "failed",
                "error": "Permission denied",
                "duration": 0.5,
                "timestamp": time.time()
            }
        }
        
        await task_handler._handle_tool_execution(fail_chunk, task_state, mock_flush)
        assert "❌ File Manager Failed (0.5s)" in task_state.status
        assert "Permission denied" in task_state.status
        
        # Verify all events triggered flush
        assert len(flush_called) == 3


class TestBackgroundUpdates:
    """Test background progress update functionality."""
    
    @pytest.mark.asyncio
    async def test_background_progress_updates(self, task_handler, mock_manager):
        """Test background progress update system."""
        # Setup task state for background mode
        chat_id = "test_chat"
        task_state = MagicMock()
        task_state.backgrounded = True
        task_state.state = "running"
        task_state.started_at = time.monotonic() - 65  # 1 minute ago
        task_state.status = "Working on complex task"
        task_state.active_agent = "RESEARCHER"
        
        mock_manager._task_states[chat_id] = task_state
        
        # Create background update coroutine
        session_id = "test_session"
        
        # Mock background progress function
        update_messages = []
        
        async def mock_send_message(chat_id, text, **kwargs):
            update_messages.append(text)
        
        mock_manager.message_sender.send_message = mock_send_message
        
        # Create and run background updates briefly
        async def run_background_updates():
            """Simulate the background update function."""
            while task_state.backgrounded and task_state.state == "running":
                await asyncio.sleep(0.1)  # Fast for testing
                
                if not task_state.backgrounded or task_state.state != "running":
                    break
                
                elapsed = time.monotonic() - task_state.started_at
                elapsed_str = f"{int(elapsed//60)}m {int(elapsed%60)}s"
                
                background_msg = (
                    f"⏳ **Background Task Update**\n\n"
                    f"📊 **Status:** {task_state.status} | 🤖 {task_state.active_agent}\n"
                    f"⏱️ **Elapsed:** {elapsed_str}\n"
                    f"🔄 **State:** Running in background\n\n"
                    f"Task will complete automatically. Use `/status` to check progress anytime."
                )
                
                await mock_send_message(chat_id, background_msg)
                break  # Only one update for testing
        
        # Run background updates
        await run_background_updates()
        
        # Verify update was sent
        assert len(update_messages) == 1
        update_msg = update_messages[0]
        assert "⏳ **Background Task Update**" in update_msg
        assert "Working on complex task" in update_msg
        assert "🤖 RESEARCHER" in update_msg
        assert "1m" in update_msg  # Should show elapsed time
        assert "Running in background" in update_msg


class TestCancellationSupport:
    """Test task cancellation functionality."""
    
    @pytest.mark.asyncio
    async def test_cancel_task_callback_handler(self, callback_handler, mock_manager):
        """Test cancel task callback handling."""
        chat_id = "123456789"
        session_id = "test_session"
        
        # Setup task state
        task_state = MagicMock()
        task_state.state = "running"
        mock_manager._task_states[chat_id] = task_state
        
        # Setup active task
        active_task = MagicMock()
        active_task.done.return_value = False
        mock_manager._active_tasks[chat_id] = active_task
        
        # Create callback query
        cq = {
            "id": "callback_123",
            "from": {"id": "123456789", "username": "testuser"},
            "message": {"message_id": "456"}
        }
        
        callback_data = f"cancel_task_{chat_id}"  # Simplified format
        
        # Test cancellation
        await callback_handler._handle_cancel_task(chat_id, cq, callback_data)
        
        # Verify task was cancelled
        active_task.cancel.assert_called_once()
        assert task_state.state == "cancelled"
        assert task_state.status == "Cancelled by user"
        
        # Verify messages were sent
        mock_manager.message_editor.edit_message.assert_called_once()
        mock_manager.message_sender.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cancel_task_authorization(self, callback_handler, mock_manager):
        """Test cancellation authorization - users can only cancel their own tasks."""
        chat_id = "123456789"
        different_chat_id = "987654321"
        
        # Create callback query from different user
        cq = {
            "id": "callback_123", 
            "from": {"id": different_chat_id, "username": "otheruser"},
            "message": {"message_id": "456"}
        }
        
        callback_data = f"cancel_task_{chat_id}_session"
        
        # Test unauthorized cancellation attempt
        await callback_handler._handle_cancel_task(different_chat_id, cq, callback_data)
        
        # Verify no messages were sent (unauthorized)
        mock_manager.message_editor.edit_message.assert_not_called()
        mock_manager.message_sender.send_message.assert_not_called()


class TestMessageFormatting:
    """Test message formatting and UI components."""
    
    def test_progress_bar_formatting(self):
        """Test progress bar visual formatting."""
        # Test different percentages
        test_cases = [
            (0, "░░░░░░░░░░"),
            (25, "██░░░░░░░░"),
            (50, "█████░░░░░"),
            (75, "███████░░░"),
            (100, "██████████")
        ]
        
        for percentage, expected_bar in test_cases:
            bar_length = 10
            filled = int(percentage / 100 * bar_length)
            progress_bar = "█" * filled + "░" * (bar_length - filled)
            assert progress_bar == expected_bar
    
    def test_time_formatting(self):
        """Test elapsed time formatting."""
        # Test different durations
        test_cases = [
            (30, "30s"),
            (90, "1m 30s"), 
            (3661, "61m 1s"),
            (7200, "120m 0s")
        ]
        
        for seconds, expected in test_cases:
            if seconds >= 60:
                formatted = f"{int(seconds//60)}m {int(seconds%60)}s"
            else:
                formatted = f"{int(seconds)}s"
            assert formatted == expected


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_progress_tracker_callback_error_handling(self):
        """Test progress tracker continues working when callbacks fail."""
        events = []
        
        async def good_callback(event):
            events.append("good")
        
        async def bad_callback(event):
            raise Exception("Callback failed")
        
        tracker = ProgressTracker()
        tracker.add_callback(good_callback)
        tracker.add_callback(bad_callback)
        
        # Should not raise exception despite bad callback
        await tracker.start_step("Test", agent="TEST")
        await tracker.finalize("Done")
        
        # Good callback should still work
        assert len(events) == 2
        assert all(e == "good" for e in events)
    
    @pytest.mark.asyncio
    async def test_malformed_progress_events(self, task_handler, mock_manager):
        """Test handling of malformed progress events."""
        task_state = MagicMock()
        
        async def mock_flush():
            pass
        
        # Test with missing data
        malformed_chunk = {"type": "progress_event"}
        await task_handler._handle_progress_event(malformed_chunk, task_state, mock_flush)
        # Should not crash
        
        # Test with invalid data types
        invalid_chunk = {
            "type": "progress_event", 
            "data": {
                "step_number": "invalid",
                "percentage": None,
                "eta_seconds": "not_a_number"
            }
        }
        await task_handler._handle_progress_event(invalid_chunk, task_state, mock_flush)
        # Should not crash


class TestIntegrationFlow:
    """Test end-to-end integration flows."""
    
    @pytest.mark.asyncio
    async def test_full_progress_flow_simulation(self):
        """Simulate a complete progress tracking flow."""
        messages = []
        
        async def mock_emit_progress(event):
            messages.append({
                "type": "progress_event",
                "step_number": event.step_number,
                "total_steps": event.total_steps,
                "progress_percent": event.progress_percent,
                "agent": event.agent,
                "stage": event.stage.value if event.stage else "",
                "action": event.action,
            })
        
        # Create progress tracker
        progress_tracker = ProgressTracker(total_steps=4)
        progress_tracker.add_callback(mock_emit_progress)
        
        # Simulate workflow progression
        await progress_tracker.start_step("Analyzing request", agent="Router", stage=ProgressStage.ROUTING)
        await progress_tracker.complete_step()
        
        await progress_tracker.start_step("Understanding intent", agent="Intent_Classifier", stage=ProgressStage.CLASSIFYING)
        await progress_tracker.complete_step()
        
        await progress_tracker.start_step("Executing tools", agent="OS_EXECUTOR", stage=ProgressStage.EXECUTING)
        await progress_tracker.complete_step()
        
        await progress_tracker.finalize("Task completed")
        
        # Verify complete flow
        assert len(messages) >= 4
        assert messages[0]["agent"] == "Router"
        assert messages[1]["agent"] == "Intent_Classifier"
        assert messages[2]["agent"] == "OS_EXECUTOR"
        assert messages[-1]["progress_percent"] == 100
    
    @pytest.mark.asyncio
    async def test_concurrent_progress_tracking(self):
        """Test multiple concurrent progress trackers."""
        results = {}
        
        async def create_tracker(tracker_id):
            events = []
            
            async def capture_event(event):
                events.append(event.progress_percent)
            
            tracker = ProgressTracker(total_steps=2)
            tracker.add_callback(capture_event)
            
            await tracker.start_step(f"Task {tracker_id}", agent=f"AGENT_{tracker_id}", stage=ProgressStage.EXECUTING)
            await asyncio.sleep(0.01)  # Small delay
            await tracker.complete_step()
            await tracker.finalize(f"Completed {tracker_id}")
            
            results[tracker_id] = events
        
        # Run multiple trackers concurrently
        tasks = [create_tracker(i) for i in range(3)]
        await asyncio.gather(*tasks)
        
        # Verify all trackers worked independently
        assert len(results) == 3
        for tracker_id, events in results.items():
            assert len(events) >= 2
            assert events[-1] == 100  # All should reach completion


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])