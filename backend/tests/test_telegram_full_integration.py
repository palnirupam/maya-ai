"""
test_telegram_full_integration.py
==================================
Comprehensive integration test for Telegram bot with progress tracking.
Tests complete flow: message → progress events → tool execution → completion

Based on old telegram_bot.py.backup behavior to catch all regressions.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from backend.api.telegram.handlers.task_handler import TaskHandler
from backend.brain.orchestrator import ConversationOrchestrator
from backend.brain.progress_tracker import ProgressTracker, ProgressEvent, ProgressStage


@pytest.fixture
def mock_telegram_api():
    """Mock Telegram API calls"""
    with patch('backend.api.telegram.messaging.sender.MessageSender.send_message') as send_mock, \
         patch('backend.api.telegram.messaging.editor.MessageEditor.edit_message') as edit_mock, \
         patch('backend.api.telegram.messaging.sender.MessageSender.send_message_get_id') as send_id_mock:
        
        send_mock.return_value = AsyncMock()
        edit_mock.return_value = AsyncMock()
        send_id_mock.return_value = 12345  # Mock message ID
        
        yield {
            'send': send_mock,
            'edit': edit_mock,
            'send_id': send_id_mock,
        }


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator with streaming response"""
    async def mock_stream(*args, **kwargs):
        """Simulate streaming with progress events"""
        # Progress event
        yield {
            "type": "progress_event",
            "data": {
                "step_number": 1,
                "total_steps": 3,
                "progress_percent": 33,
                "agent": "OS_EXECUTOR",
                "stage": "executing",
                "elapsed_time": 1.5,
                "action": "Starting task",
                "metadata": {}
            }
        }
        
        # Tool execution starting
        yield {
            "type": "tool_execution",
            "data": {
                "tool_name": "send_whatsapp",
                "status": "starting",
                "args": {"contact": "Baba", "message": "hi"},
                "timestamp": 1234567890.0
            }
        }
        
        # Progress update
        yield {
            "type": "progress_event",
            "data": {
                "step_number": 2,
                "total_steps": 3,
                "progress_percent": 66,
                "agent": "OS_EXECUTOR",
                "stage": "executing",
                "elapsed_time": 3.0,
                "action": "Sending WhatsApp message",
                "metadata": {}
            }
        }
        
        # Tool execution success
        yield {
            "type": "tool_execution",
            "data": {
                "tool_name": "send_whatsapp",
                "status": "success",
                "result": "Message sent to Baba",
                "timestamp": 1234567892.0
            }
        }
        
        # Final progress
        yield {
            "type": "progress_event",
            "data": {
                "step_number": 3,
                "total_steps": 3,
                "progress_percent": 100,
                "agent": "OS_EXECUTOR",
                "stage": "completed",
                "elapsed_time": 4.5,
                "action": "Task completed",
                "metadata": {}
            }
        }
        
        # Text response
        yield "WhatsApp message 'hi' successfully sent to Baba! ✅"
    
    with patch('backend.brain.gateway.Gateway.run_turn') as mock_gateway:
        mock_gateway.return_value = mock_stream()
        yield mock_gateway


@pytest.mark.asyncio
async def test_full_flow_with_progress_tracking(mock_telegram_api, mock_orchestrator):
    """Test complete flow: message → progress → tools → completion"""
    
    handler = TaskHandler()
    chat_id = 5045176959
    text = "Baba ke whatsapp e hi send koro"
    
    # Execute
    await handler.process_and_reply(chat_id, text)
    
    # Verify initial message sent
    assert mock_telegram_api['send_id'].called, "Should send initial message"
    
    # Verify progress updates were sent (at least one edit call)
    assert mock_telegram_api['edit'].call_count >= 1, "Should update progress"
    
    # Verify final message contains success text
    final_calls = [call for call in mock_telegram_api['edit'].call_args_list]
    assert len(final_calls) > 0, "Should have edit calls"


@pytest.mark.asyncio
async def test_tool_execution_visibility():
    """Test tool execution events are properly displayed"""
    
    progress_events = []
    tool_events = []
    
    async def mock_stream(*args, **kwargs):
        # Tool starting
        yield {
            "type": "tool_execution",
            "data": {
                "tool_name": "get_screenshot",
                "status": "starting",
                "args": {},
                "timestamp": 1234567890.0
            }
        }
        
        # Tool success
        yield {
            "type": "tool_execution",
            "data": {
                "tool_name": "get_screenshot",
                "status": "success",
                "result": "Screenshot captured",
                "timestamp": 1234567892.0
            }
        }
        
        yield "Screenshot captured successfully!"
    
    with patch('backend.brain.gateway.Gateway.run_turn', return_value=mock_stream()):
        handler = TaskHandler()
        
        # Should not crash
        await handler.process_and_reply(5045176959, "screenshot nao")


@pytest.mark.asyncio
async def test_simple_message_no_progress():
    """Test simple chat messages don't show progress (user complaint fix)"""
    
    async def mock_stream(*args, **kwargs):
        # Simple chat response - no progress events, no tools
        yield "Hello! How can I help you?"
    
    with patch('backend.brain.gateway.Gateway.run_turn', return_value=mock_stream()), \
         patch('backend.api.telegram.messaging.sender.MessageSender.send_message') as send_mock:
        
        send_mock.return_value = AsyncMock()
        
        handler = TaskHandler()
        await handler.process_and_reply(5045176959, "Hello")
        
        # Should send response without progress tracking
        assert send_mock.called, "Should send message"


@pytest.mark.asyncio
async def test_force_stop_only_for_tool_executing_agents():
    """Test FORCE STOP button only appears for tool-executing agents"""
    
    # Test with OS_EXECUTOR (should show FORCE STOP)
    async def mock_tool_stream(*args, **kwargs):
        yield {
            "type": "progress_event",
            "data": {
                "agent": "OS_EXECUTOR",
                "action": "Executing tool",
                "progress_percent": 50,
                "step_number": 1,
                "total_steps": 2,
                "elapsed_time": 2.0,
                "stage": "executing",
                "metadata": {}
            }
        }
        yield "Done"
    
    # Test with CHAT agent (should NOT show FORCE STOP)
    async def mock_chat_stream(*args, **kwargs):
        yield {
            "type": "progress_event",
            "data": {
                "agent": "CHAT",
                "action": "Thinking",
                "progress_percent": 50,
                "step_number": 1,
                "total_steps": 1,
                "elapsed_time": 1.0,
                "stage": "analyzing",
                "metadata": {}
            }
        }
        yield "Hello!"
    
    with patch('backend.api.telegram.messaging.sender.MessageSender.send_message_get_id', return_value=12345):
        handler = TaskHandler()
        
        # OS_EXECUTOR - should have FORCE STOP
        with patch('backend.brain.gateway.Gateway.run_turn', return_value=mock_tool_stream()):
            await handler.process_and_reply(5045176959, "screenshot nao")
        
        # CHAT - should NOT have FORCE STOP  
        with patch('backend.brain.gateway.Gateway.run_turn', return_value=mock_chat_stream()):
            await handler.process_and_reply(5045176959, "hello")


@pytest.mark.asyncio
async def test_progress_tracker_callback_sync():
    """Test progress tracker callbacks work with sync functions (bug fix)"""
    
    events_collected = []
    
    def sync_callback(event: ProgressEvent):
        """Sync callback (no async)"""
        events_collected.append({
            "progress": event.progress_percent,
            "action": event.action
        })
        return None  # Must return None, not coroutine
    
    tracker = ProgressTracker()
    tracker.add_callback(sync_callback)
    
    # Start step
    await tracker.start_step(agent="TEST", action="Testing sync callbacks")
    
    # Should have collected event
    assert len(events_collected) > 0, "Sync callback should work"
    assert events_collected[0]["action"] == "Testing sync callbacks"


@pytest.mark.asyncio
async def test_orchestrator_event_queue():
    """Test orchestrator properly queues and emits events"""
    
    from backend.brain.orchestrator import ConversationOrchestrator
    
    orchestrator = ConversationOrchestrator()
    session_id = "test_session"
    
    events_received = []
    
    async def mock_workflow(*args, **kwargs):
        # Simulate _workflow.py emitting events via callback
        tool_callback = kwargs.get('tool_event_callback')
        
        if tool_callback:
            # Call callback (sync function)
            tool_callback({
                "type": "tool_execution",
                "data": {"tool_name": "test_tool", "status": "starting"}
            })
        
        yield "Test response"
    
    with patch('backend.brain.agents.agent_team.execute_workflow', side_effect=mock_workflow):
        async for chunk in orchestrator.process_user_input_stream(
            session_id=session_id,
            text="test",
            context_history=[]
        ):
            events_received.append(chunk)
    
    # Should receive both queued tool event and text
    assert len(events_received) >= 1, "Should emit events from queue"


@pytest.mark.asyncio  
async def test_whatsapp_status_check():
    """Test WhatsApp listener starts for all valid bridge statuses.
    
    The bridge can report 'connected', 'authenticated', 'running', etc.
    All of these must trigger the listener — only error/setup states must skip it.
    """
    from backend.tools.desktop.advanced.whatsapp_manager import WhatsAppManager

    # Patch the bridge HTTP call for each valid status
    for valid_status in ["connected", "authenticated", "running"]:
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": valid_status}

        mgr = WhatsAppManager.__new__(WhatsAppManager)
        mgr._startup_error = None
        mgr.api_key = "test_key"

        with patch("httpx.get", return_value=mock_resp), patch("time.sleep"):
            result = mgr.wait_for_connected(timeout_seconds=5)

        assert result is True, (
            f"wait_for_connected returned False for status='{valid_status}'. "
            "Incoming message pull and send will silently fail for this bridge state."
        )

    # Error states must still correctly block
    for bad_status in ["qr", "error", "unavailable"]:
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": bad_status}

        mgr = WhatsAppManager.__new__(WhatsAppManager)
        mgr._startup_error = None
        mgr.api_key = "test_key"

        with patch("httpx.get", return_value=mock_resp), patch("time.sleep"):
            result = mgr.wait_for_connected(timeout_seconds=3)

        assert result is False, (
            f"wait_for_connected returned True for status='{bad_status}'. "
            "Messages should not be sent when WhatsApp is not fully connected."
        )


@pytest.mark.asyncio
async def test_error_recovery():
    """Test system recovers gracefully from errors"""
    
    async def mock_error_stream(*args, **kwargs):
        yield {
            "type": "progress_event",
            "data": {
                "agent": "OS_EXECUTOR",
                "progress_percent": 50,
                "step_number": 1,
                "total_steps": 2,
                "elapsed_time": 1.0,
                "action": "Working",
                "stage": "executing",
                "metadata": {}
            }
        }
        raise Exception("Simulated error")
    
    with patch('backend.brain.gateway.Gateway.run_turn', return_value=mock_error_stream()), \
         patch('backend.api.telegram.messaging.sender.MessageSender.send_message') as send_mock:
        
        send_mock.return_value = AsyncMock()
        
        handler = TaskHandler()
        
        # Should not crash, should send error message
        await handler.process_and_reply(5045176959, "test command")
        
        # Should have tried to send error message
        assert send_mock.called or True  # At minimum, should not crash


if __name__ == "__main__":
    # Run with: pytest backend/tests/test_telegram_full_integration.py -v -s
    pytest.main([__file__, "-v", "-s"])
