"""
telegram/core/state_models.py
==============================
Typed state containers for Telegram bot state management.

Replaces raw dictionaries with proper dataclasses for type safety
and better maintainability.
"""

import time
from dataclasses import dataclass, field
from typing import List


@dataclass
class PendingWAReply:
    """
    Holds all state for one incoming WhatsApp message awaiting action.
    
    This represents a WhatsApp message that has been received and is
    waiting for the user to decide how to respond (auto-reply, manual, ignore).
    
    Attributes:
        id: Unique identifier for this pending reply
        chat_id_wa: WhatsApp chat ID for whatsapp_manager.reply_to_chat
        from_number: Phone number of the sender
        from_name: Display name of the sender
        is_group: True if this is a group message
        group_name: Name of the group (if is_group is True)
        trigger_msg: The incoming WhatsApp message text
        context_messages: Previous messages in the conversation for context
        is_known: True if sender is in contact list
        gemini_draft: AI-generated draft reply
        created_at: Timestamp when this pending reply was created
    """
    id: str
    chat_id_wa: str
    from_number: str
    from_name: str
    is_group: bool
    group_name: str
    trigger_msg: str
    context_messages: List[dict]
    is_known: bool
    gemini_draft: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class PendingDangerousCmd:
    """
    Confirmation state for a dangerous command (shutdown, etc.).
    
    When a user issues a potentially dangerous command like system shutdown,
    this state is stored to track the confirmation requirement.
    
    Attributes:
        telegram_chat_id: Telegram chat ID that issued the command
        original_text: The original command text from the user
    """
    telegram_chat_id: str
    original_text: str


@dataclass
class TelegramTaskState:
    """
    Progress snapshot for the latest orchestrator task in one chat.
    
    Tracks the execution state of an active or recently completed task,
    allowing status queries and background execution monitoring.
    
    Attributes:
        original_text: The original user message that triggered the task
        session_id: Unique session identifier for this task
        started_at: Monotonic timestamp when task started
        updated_at: Monotonic timestamp of last update
        state: Current state: "running", "completed", "failed", "timed_out", "cancelled"
        active_agent: Name of the currently active agent
        status: Human-readable status message
        backgrounded: True if task is running in background
        final_text: Final response text when completed
        error: Error message if failed
    """
    original_text: str
    session_id: str
    started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    state: str = "running"
    active_agent: str = ""
    status: str = "Starting task..."
    backgrounded: bool = False
    final_text: str = ""
    error: str = ""
