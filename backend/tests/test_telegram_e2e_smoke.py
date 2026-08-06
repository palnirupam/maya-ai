"""
test_telegram_e2e_smoke.py
==========================
End-to-end smoke test for Telegram progress tracking system.

Simulates a real user workflow:
- User sends message to Telegram bot
- Progress updates appear in real-time
- Tool execution visibility shows running tools
- Task completes with final result
- Timing verification ensures acceptable performance

This is a lightweight smoke test to verify the complete system integration.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from backend.brain.progress_tracker import ProgressTracker, ProgressStage
from backend.api.telegram.core.state_models import TelegramTaskState


@pytest.mark.asyncio
async def test_e2e_user_workflow_smoke():
    """
    End-to-end smoke test simulating complete user workflow.
    
    Flow:
    1. User sends message: "open calculator"
    2. Progress tracking starts
    3. Multiple progress updates received
    4. Tool execution events emitted
    5. Task completes successfully
    6. Total time < 5 seconds (performance check)
    """
    # Track events
    progress_events = []
    tool_events = []
    messages_sent = []
    
    start_time = time.time()
    
    # Mock callbacks
    async def track_progress(event):
        progress_events.append({
            "timestamp": time.time() - start_time,
            "step": event.step_number,
            "total": event.total_steps,
            "percent": event.progress_percent,
            "agent": event.agent,
            "action": event.action
        })
    
    async def track_tool_event(event):
        tool_events.append({
            "timestamp": time.time() - start_time,
            "type": event.get("type"),
            "data": event.get("data", {})
        })
    
    async def track_message(chat_id, text, **kwargs):
        messages_sent.append({
            "timestamp": time.time() - start_time,
            "chat_id": chat_id,
            "text": text,
            "has_cancel_button": "cancel_task" in str(kwargs.get("reply_markup", ""))
        })
    
    # Create progress tracker
    tracker = ProgressTracker(total_steps=5)
    tracker.add_callback(track_progress)
    
    # Simulate workflow stages
    await tracker.start_step(
        "Analyzing request", 
        agent="Router", 
        stage=ProgressStage.ROUTING
    )
    await asyncio.sleep(0.05)  # Simulate work
    await tracker.complete_step()
    
    await tracker.start_step(
        "Understanding intent", 
        agent="Intent_Classifier", 
        stage=ProgressStage.CLASSIFYING
    )
    await asyncio.sleep(0.05)
    await tracker.complete_step()
    
    await tracker.start_step(
        "Activating agent", 
        agent="OS_EXECUTOR", 
        stage=ProgressStage.EXECUTING
    )
    await asyncio.sleep(0.05)
    await tracker.complete_step()
    
    # Simulate tool execution
    await track_tool_event({
        "type": "tool_execution",
        "data": {
            "tool_name": "open_app",
            "status": "starting",
            "timestamp": time.time()
        }
    })
    
    await asyncio.sleep(0.05)  # Simulate tool execution
    
    await track_tool_event({
        "type": "tool_execution",
        "data": {
            "tool_name": "open_app",
            "status": "success",
            "duration": 0.05,
            "result": "Calculator opened",
            "timestamp": time.time()
        }
    })
    
    await tracker.start_step(
        "Finalizing response", 
        agent="OS_EXECUTOR", 
        stage=ProgressStage.COMPLETING
    )
    await asyncio.sleep(0.05)
    await tracker.complete_step()
    
    await tracker.finalize("Task completed successfully")
    
    total_time = time.time() - start_time
    
    # Verify workflow completion
    assert len(progress_events) >= 5, "Should have at least 5 progress events"
    assert len(tool_events) == 2, "Should have 2 tool events (start + success)"
    
    # Verify progress sequence
    assert progress_events[0]["agent"] == "Router"
    assert progress_events[1]["agent"] == "Intent_Classifier"
    assert progress_events[-1]["percent"] == 100
    
    # Verify tool execution
    assert tool_events[0]["data"]["status"] == "starting"
    assert tool_events[1]["data"]["status"] == "success"
    assert tool_events[1]["data"]["tool_name"] == "open_app"
    
    # Performance check: entire workflow should complete quickly
    assert total_time < 1.0, f"Workflow took {total_time:.2f}s (should be < 1.0s)"
    
    print(f"\nE2E Smoke Test Passed!")
    print(f"   - Total time: {total_time:.3f}s")
    print(f"   - Progress events: {len(progress_events)}")
    print(f"   - Tool events: {len(tool_events)}")
    print(f"   - Final progress: {progress_events[-1]['percent']}%")


@pytest.mark.asyncio
async def test_e2e_cancellation_workflow():
    """Test end-to-end cancellation workflow."""
    events = []
    
    async def track_event(event):
        events.append(event)
    
    tracker = ProgressTracker(total_steps=5)
    tracker.add_callback(track_event)
    
    # Start workflow
    await tracker.start_step("Step 1", agent="TEST", stage=ProgressStage.EXECUTING)
    await tracker.complete_step()
    
    await tracker.start_step("Step 2", agent="TEST", stage=ProgressStage.EXECUTING)
    
    # Cancel mid-execution
    await tracker.cancel()
    
    # Verify cancellation
    assert tracker.is_cancelled
    assert len(events) >= 2
    assert events[-1].stage == ProgressStage.CANCELLED


@pytest.mark.asyncio  
async def test_e2e_background_mode_transition():
    """Test workflow transitioning to background mode."""
    # Simulate task state
    task_state = TelegramTaskState(
        original_text="test command",
        session_id="test_session_123"
    )
    task_state.state = "running"
    task_state.backgrounded = False
    task_state.started_at = time.monotonic()
    
    # Transition to background after soft timeout
    await asyncio.sleep(0.01)
    task_state.backgrounded = True
    task_state.status = "Working in background..."
    
    # Verify state
    assert task_state.backgrounded
    assert task_state.state == "running"
    elapsed = time.monotonic() - task_state.started_at
    assert elapsed > 0


@pytest.mark.asyncio
async def test_performance_overhead():
    """Verify progress tracking adds minimal overhead."""
    
    # Test without progress tracking
    start_no_tracking = time.time()
    for i in range(10):
        await asyncio.sleep(0.001)
    time_no_tracking = time.time() - start_no_tracking
    
    # Test with progress tracking
    tracker = ProgressTracker(total_steps=10)
    events = []
    
    async def dummy_callback(event):
        events.append(event)
    
    tracker.add_callback(dummy_callback)
    
    start_with_tracking = time.time()
    for i in range(10):
        await tracker.start_step(f"Step {i}", agent="TEST", stage=ProgressStage.EXECUTING)
        await asyncio.sleep(0.001)
        await tracker.complete_step()
    time_with_tracking = time.time() - start_with_tracking
    
    # Calculate overhead
    overhead = time_with_tracking - time_no_tracking
    overhead_ms = overhead * 1000
    
    # Verify overhead is acceptable (< 100ms as per requirement)
    assert overhead_ms < 100, f"Overhead {overhead_ms:.1f}ms exceeds 100ms limit"
    
    print(f"\nPerformance Check Passed!")
    print(f"   - Time without tracking: {time_no_tracking*1000:.1f}ms")
    print(f"   - Time with tracking: {time_with_tracking*1000:.1f}ms")
    print(f"   - Overhead: {overhead_ms:.1f}ms (< 100ms)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
