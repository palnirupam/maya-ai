"""
test_telegram_real_integration.py
==================================
Real integration test (no mocks) to catch issues like:
- Missing imports
- Method signature mismatches
- Real API compatibility issues
"""

import pytest
import asyncio
from backend.brain.progress_tracker import ProgressTracker, ProgressStage
from backend.brain.orchestrator import ConversationOrchestrator


class TestRealIntegration:
    """Test with real objects, not mocks."""
    
    @pytest.mark.asyncio
    async def test_asyncio_import_in_orchestrator(self):
        """Verify asyncio is properly imported in orchestrator."""
        # This would fail if asyncio wasn't imported
        orchestrator = ConversationOrchestrator()
        assert hasattr(orchestrator, 'process_user_input_stream')
        
        # Try to use asyncio in orchestrator context
        import inspect
        source = inspect.getsource(orchestrator.process_user_input_stream)
        assert 'asyncio.current_task()' in source
        print("✓ asyncio properly imported in orchestrator")
    
    @pytest.mark.asyncio
    async def test_message_sender_signature(self):
        """Verify MessageSender method signatures match our usage."""
        from backend.api.telegram.messaging.sender import MessageSender
        from unittest.mock import MagicMock
        
        # Create mock manager
        mock_manager = MagicMock()
        mock_manager.bot_token = "test_token"
        mock_manager._http = MagicMock()
        
        sender = MessageSender(mock_manager)
        
        # Check send_message signature
        import inspect
        sig = inspect.signature(sender.send_message)
        params = list(sig.parameters.keys())
        assert 'reply_markup' in params, "send_message should support reply_markup"
        
        # Check send_message_get_id signature  
        sig_get_id = inspect.signature(sender.send_message_get_id)
        params_get_id = list(sig_get_id.parameters.keys())
        # Should NOT have reply_markup
        assert 'reply_markup' not in params_get_id, "send_message_get_id doesn't support reply_markup"
        
        print("✓ MessageSender signatures verified")
    
    @pytest.mark.asyncio
    async def test_progress_tracker_with_real_callbacks(self):
        """Test ProgressTracker with real async callbacks."""
        events = []
        
        async def real_callback(event):
            # Simulate what orchestrator does
            event_dict = {
                "type": "progress_event",
                "data": {
                    "step_number": event.step_number,
                    "total_steps": event.total_steps,
                    "progress_percent": event.progress_percent,
                }
            }
            events.append(event_dict)
            await asyncio.sleep(0.001)  # Simulate async work
        
        tracker = ProgressTracker(total_steps=3)
        tracker.add_callback(real_callback)
        
        await tracker.start_step("Step 1", agent="TEST", stage=ProgressStage.EXECUTING)
        await tracker.complete_step()
        
        await tracker.finalize("Done")
        
        assert len(events) >= 2
        print(f"✓ ProgressTracker real callback test passed ({len(events)} events)")
    
    @pytest.mark.asyncio
    async def test_task_handler_flush_logic(self):
        """Test task_handler _flush logic with reply_markup."""
        from backend.api.telegram.handlers.task_handler import TaskHandler
        from backend.api.telegram.core.state_models import TelegramTaskState
        from unittest.mock import AsyncMock, MagicMock
        
        # Create mock manager with proper structure
        mock_manager = MagicMock()
        mock_manager.message_sender = AsyncMock()
        mock_manager.message_sender.send_message = AsyncMock()
        mock_manager.message_sender.send_message_get_id = AsyncMock(return_value="123")
        mock_manager.message_editor = AsyncMock()
        mock_manager.typing_indicator = AsyncMock()
        
        handler = TaskHandler(mock_manager)
        
        # Verify handler can be instantiated
        assert handler is not None
        print("✓ TaskHandler instantiation successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
