"""
test_telegram_stream_fix.py
============================
Simple test to verify progress tracking stream fix.
Tests that sync callbacks work and events are properly queued.
"""

import asyncio
import pytest
from backend.brain.progress_tracker import ProgressTracker, ProgressEvent


@pytest.mark.asyncio
async def test_sync_callback_works():
    """Test that sync callbacks work without 'async_generator' error"""
    
    events_collected = []
    
    def sync_callback(event: ProgressEvent):
        """Sync callback - no async, no yield"""
        events_collected.append({
            "progress": event.progress_percent,
            "action": event.action,
            "agent": event.agent
        })
        return None  # Must return None, not a coroutine
    
    tracker = ProgressTracker()
    tracker.add_callback(sync_callback)
    
    # Start step - should trigger callback
    await tracker.start_step(agent="OS_EXECUTOR", action="Testing sync callbacks")
    
    # Verify callback was called
    assert len(events_collected) > 0, "Sync callback should have been called"
    assert events_collected[0]["agent"] == "OS_EXECUTOR"
    assert events_collected[0]["action"] == "Testing sync callbacks"
    
    print(f"✅ Collected {len(events_collected)} events from sync callback")


@pytest.mark.asyncio
async def test_multiple_progress_updates():
    """Test multiple progress updates work correctly"""
    
    events = []
    
    def collector(event: ProgressEvent):
        events.append(event.progress_percent)
        return None
    
    tracker = ProgressTracker(total_steps=3)
    tracker.add_callback(collector)
    
    # Step 1
    await tracker.start_step(agent="TEST", action="Step 1")
    await tracker.complete_step()
    
    # Step 2
    await tracker.start_step(agent="TEST", action="Step 2")
    await tracker.complete_step()
    
    # Step 3
    await tracker.start_step(agent="TEST", action="Step 3")
    await tracker.complete_step()
    
    # Should have received progress updates
    assert len(events) >= 3, f"Should have at least 3 events, got {len(events)}"
    print(f"✅ Progress percentages: {events}")


@pytest.mark.asyncio
async def test_event_queue_pattern():
    """Test event queue pattern used in orchestrator"""
    
    # Simulate orchestrator's event queue pattern
    events_queue = []
    
    def queue_event(event):
        """Queue event for emission"""
        events_queue.append({
            "type": "test_event",
            "data": {"value": event.progress_percent}
        })
        return None
    
    tracker = ProgressTracker(total_steps=2)
    tracker.add_callback(queue_event)
    
    # Generate events
    await tracker.start_step(agent="TEST", action="Action 1")
    await tracker.complete_step()
    
    # Emit queued events (like orchestrator does)
    emitted = []
    while events_queue:
        emitted.append(events_queue.pop(0))
    
    assert len(emitted) >= 1, "Should have queued events"
    assert emitted[0]["type"] == "test_event"
    print(f"✅ Emitted {len(emitted)} queued events")


@pytest.mark.asyncio
async def test_no_async_generator_error():
    """Test that we don't get 'async_generator' object can't be awaited error"""
    
    error_occurred = False
    
    def simple_callback(event: ProgressEvent):
        # This is sync, returns None
        return None
    
    tracker = ProgressTracker()
    tracker.add_callback(simple_callback)
    
    try:
        await tracker.start_step(agent="TEST", action="Test action")
        await tracker.update_progress(metadata={"test": "value"})
        await tracker.complete_step()
    except TypeError as e:
        if "async_generator" in str(e):
            error_occurred = True
            pytest.fail(f"Got async_generator error: {e}")
    
    assert not error_occurred, "Should not get async_generator error"
    print("✅ No async_generator errors")


if __name__ == "__main__":
    # Run with: pytest backend/tests/test_telegram_stream_fix.py -v -s
    pytest.main([__file__, "-v", "-s"])
