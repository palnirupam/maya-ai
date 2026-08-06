"""
Progress Tracking System for Real-time User Feedback
=====================================================

Provides granular progress tracking for long-running operations with:
- Step-by-step progress events
- Percentage calculation
- Time estimation
- Agent/stage tracking
- Multi-callback broadcasting

Usage:
    tracker = ProgressTracker(total_steps=5)
    tracker.add_callback(telegram_callback)
    
    await tracker.start_step("Analyzing request...", agent="Router")
    # ... do work ...
    await tracker.complete_step()
    
    await tracker.start_step("Executing command...", agent="OS_Executor")
    # ... do work ...
    await tracker.complete_step()

Author: Maya AI Team
Version: 1.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Awaitable

logger = logging.getLogger(__name__)


class ProgressStage(Enum):
    """Workflow execution stages"""
    INITIALIZING = "initializing"
    ROUTING = "routing"
    CLASSIFYING = "classifying"
    EXECUTING = "executing"
    COMPLETING = "completing"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressEvent:
    """
    Granular progress event for streaming to user.
    
    Attributes:
        step_number: Current step (1-indexed)
        total_steps: Total expected steps (may be estimated)
        stage: Current workflow stage
        action: Human-readable description of current action
        agent: Name of active agent (e.g., "Router", "OS_Executor")
        progress_percent: Overall progress (0-100)
        estimated_time_left: Estimated seconds remaining (None if unknown)
        elapsed_time: Seconds elapsed since tracking started
        metadata: Additional context-specific data
    """
    step_number: int
    total_steps: int
    stage: ProgressStage
    action: str
    agent: str
    progress_percent: int
    estimated_time_left: Optional[int] = None
    elapsed_time: float = 0.0
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate event data"""
        assert 0 <= self.step_number <= self.total_steps, \
            f"Invalid step: {self.step_number}/{self.total_steps}"
        assert 0 <= self.progress_percent <= 100, \
            f"Invalid progress: {self.progress_percent}%"
        assert self.agent, "Agent name is required"
        assert self.action, "Action description is required"


class ProgressTracker:
    """
    Tracks and broadcasts progress events during workflow execution.
    
    Features:
    - Automatic percentage calculation
    - Time estimation based on historical data
    - Multi-callback broadcasting
    - Thread-safe operation
    - Automatic cleanup
    
    Example:
        async def progress_callback(event: ProgressEvent):
            print(f"{event.action} - {event.progress_percent}%")
        
        tracker = ProgressTracker(total_steps=3)
        tracker.add_callback(progress_callback)
        
        await tracker.start_step("Step 1", agent="TestAgent")
        await asyncio.sleep(1)
        await tracker.complete_step()
        
        await tracker.start_step("Step 2", agent="TestAgent")
        await asyncio.sleep(1)
        await tracker.complete_step()
        
        await tracker.finalize("All done!")
    """
    
    def __init__(
        self,
        total_steps: int = 5,
        enable_time_estimation: bool = True,
        estimation_window: int = 3,
    ):
        """
        Initialize progress tracker.
        
        Args:
            total_steps: Expected number of steps (can be adjusted dynamically)
            enable_time_estimation: Whether to estimate time remaining
            estimation_window: Number of recent steps to use for time estimation
        """
        self.total_steps = total_steps
        self.enable_time_estimation = enable_time_estimation
        self.estimation_window = estimation_window
        
        # State
        self.current_step = 0
        self.current_stage = ProgressStage.INITIALIZING
        self.current_agent = ""
        self.current_action = ""
        self.started_at = time.monotonic()
        self.step_start_time = 0.0
        self.is_cancelled = False
        self.is_completed = False
        
        # Historical data for time estimation
        self._step_durations: list[float] = []
        
        # Callbacks
        self._callbacks: list[Callable[[ProgressEvent], Awaitable[None]]] = []
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    def add_callback(self, callback: Callable[[ProgressEvent], Awaitable[None]]) -> None:
        """
        Add a callback to receive progress events.
        
        Args:
            callback: Async function that receives ProgressEvent
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[ProgressEvent], Awaitable[None]]) -> None:
        """Remove a previously registered callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def clear_callbacks(self) -> None:
        """Remove all callbacks"""
        self._callbacks.clear()
    
    async def start_step(
        self,
        action: str,
        agent: str,
        stage: Optional[ProgressStage] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Mark the beginning of a new step.
        
        Args:
            action: Human-readable description (e.g., "Opening Chrome browser...")
            agent: Agent name (e.g., "OS_Executor")
            stage: Workflow stage (auto-detected if None)
            metadata: Additional context data
        """
        async with self._lock:
            if self.is_cancelled:
                logger.warning("Cannot start step - tracker is cancelled")
                return
            
            # Complete previous step if any
            if self.current_step > 0:
                await self._record_step_duration()
            
            # Advance to next step
            self.current_step += 1
            self.current_action = action
            self.current_agent = agent
            self.current_stage = stage or self._detect_stage(action, agent)
            self.step_start_time = time.monotonic()
            
            # Emit event
            event = self._create_event(metadata or {})
            await self._emit(event)
    
    async def update_progress(
        self,
        action: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Update the current step's action without advancing step counter.
        
        Useful for showing sub-progress within a step.
        
        Args:
            action: Updated action description
            metadata: Additional context data
        """
        async with self._lock:
            if self.is_cancelled or self.current_step == 0:
                return
            
            if action:
                self.current_action = action
            
            event = self._create_event(metadata or {})
            await self._emit(event)
    
    async def complete_step(self) -> None:
        """
        Mark the current step as complete.
        
        Records the step duration for time estimation.
        """
        async with self._lock:
            if self.current_step > 0:
                await self._record_step_duration()
    
    async def adjust_total_steps(self, new_total: int) -> None:
        """
        Dynamically adjust total steps.
        
        Useful when the actual number of steps becomes known during execution.
        
        Args:
            new_total: New total step count
        """
        async with self._lock:
            old_total = self.total_steps
            self.total_steps = max(new_total, self.current_step)
            logger.debug(
                f"[ProgressTracker] Adjusted total steps: {old_total} → {self.total_steps}"
            )
    
    async def cancel(self) -> None:
        """
        Mark the tracker as cancelled.
        
        Emits a final cancellation event and prevents further updates.
        """
        async with self._lock:
            if self.is_cancelled or self.is_completed:
                return
            
            self.is_cancelled = True
            self.current_stage = ProgressStage.CANCELLED
            
            event = self._create_event({"cancelled": True})
            await self._emit(event)
    
    async def fail(self, error_message: str) -> None:
        """
        Mark the tracker as failed.
        
        Args:
            error_message: Description of the failure
        """
        async with self._lock:
            if self.is_completed:
                return
            
            self.is_cancelled = True  # Prevent further updates
            self.current_stage = ProgressStage.FAILED
            self.current_action = f"Failed: {error_message}"
            
            event = self._create_event({"error": error_message})
            await self._emit(event)
    
    async def finalize(self, final_message: str = "Completed") -> None:
        """
        Mark tracking as complete.
        
        Emits a final 100% progress event.
        
        Args:
            final_message: Final action description
        """
        async with self._lock:
            if self.is_completed:
                return
            
            self.is_completed = True
            self.current_step = self.total_steps
            self.current_stage = ProgressStage.COMPLETING
            self.current_action = final_message
            
            # Final event with 100% progress
            event = ProgressEvent(
                step_number=self.total_steps,
                total_steps=self.total_steps,
                stage=ProgressStage.COMPLETING,
                action=final_message,
                agent=self.current_agent or "System",
                progress_percent=100,
                elapsed_time=time.monotonic() - self.started_at,
                metadata={"final": True},
            )
            
            await self._emit(event)
    
    def _create_event(self, metadata: dict) -> ProgressEvent:
        """
        Create a progress event from current state.
        
        Args:
            metadata: Additional event metadata
            
        Returns:
            ProgressEvent with current progress information
        """
        progress_percent = int((self.current_step / self.total_steps) * 100)
        progress_percent = min(progress_percent, 99)  # Reserve 100% for finalize()
        
        elapsed = time.monotonic() - self.started_at
        
        # Estimate time remaining
        eta = None
        if self.enable_time_estimation and self._step_durations:
            eta = self._estimate_time_remaining()
        
        return ProgressEvent(
            step_number=self.current_step,
            total_steps=self.total_steps,
            stage=self.current_stage,
            action=self.current_action,
            agent=self.current_agent,
            progress_percent=progress_percent,
            estimated_time_left=eta,
            elapsed_time=elapsed,
            metadata=metadata,
        )
    
    async def _emit(self, event: ProgressEvent) -> None:
        """
        Broadcast event to all registered callbacks.
        
        Args:
            event: Progress event to broadcast
        """
        if not self._callbacks:
            return
        
        # Call all callbacks concurrently
        tasks = []
        for callback in self._callbacks:
            try:
                task = callback(event)
                if asyncio.iscoroutine(task):
                    tasks.append(task)
            except Exception as e:
                logger.error(f"[ProgressTracker] Callback error: {e}", exc_info=True)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _record_step_duration(self) -> None:
        """Record the duration of the current step for time estimation"""
        if self.step_start_time > 0:
            duration = time.monotonic() - self.step_start_time
            self._step_durations.append(duration)
            
            # Keep only recent durations (sliding window)
            if len(self._step_durations) > self.estimation_window:
                self._step_durations.pop(0)
    
    def _estimate_time_remaining(self) -> Optional[int]:
        """
        Estimate seconds remaining based on historical step durations.
        
        Returns:
            Estimated seconds, or None if insufficient data
        """
        if not self._step_durations:
            return None
        
        # Average duration of recent steps
        avg_duration = sum(self._step_durations) / len(self._step_durations)
        
        # Remaining steps
        remaining_steps = self.total_steps - self.current_step
        
        # Estimate
        estimated_seconds = int(avg_duration * remaining_steps)
        
        return max(estimated_seconds, 1)  # At least 1 second
    
    @staticmethod
    def _detect_stage(action: str, agent: str) -> ProgressStage:
        """
        Auto-detect workflow stage from action/agent.
        
        Args:
            action: Action description
            agent: Agent name
            
        Returns:
            Detected ProgressStage
        """
        action_lower = action.lower()
        
        if "rout" in action_lower or "analyz" in action_lower:
            return ProgressStage.ROUTING
        elif "classif" in action_lower or "intent" in action_lower:
            return ProgressStage.CLASSIFYING
        elif "execut" in action_lower or "running" in action_lower:
            return ProgressStage.EXECUTING
        elif "complet" in action_lower or "finish" in action_lower:
            return ProgressStage.COMPLETING
        
        return ProgressStage.EXECUTING  # Default
    
    @property
    def progress_percent(self) -> int:
        """Get current progress percentage"""
        if self.total_steps == 0:
            return 0
        return int((self.current_step / self.total_steps) * 100)
    
    @property
    def elapsed_seconds(self) -> int:
        """Get elapsed seconds since tracking started"""
        return int(time.monotonic() - self.started_at)
    
    def __repr__(self) -> str:
        return (
            f"ProgressTracker(step={self.current_step}/{self.total_steps}, "
            f"progress={self.progress_percent}%, agent={self.current_agent})"
        )


# Convenience function for creating trackers
def create_tracker(
    total_steps: int = 5,
    callbacks: Optional[list[Callable[[ProgressEvent], Awaitable[None]]]] = None,
) -> ProgressTracker:
    """
    Create a ProgressTracker with optional callbacks.
    
    Args:
        total_steps: Expected number of steps
        callbacks: List of async callbacks to register
        
    Returns:
        Configured ProgressTracker instance
    """
    tracker = ProgressTracker(total_steps=total_steps)
    
    if callbacks:
        for callback in callbacks:
            tracker.add_callback(callback)
    
    return tracker
