from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Float
from sqlalchemy.sql import func
from .connection import Base

class SessionMemory(Base):
    __tablename__ = "session_memory"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    role = Column(String) # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(JSON) # Store interaction style, UI themes, etc.

class ToolHistory(Base):
    __tablename__ = "tool_history"

    id = Column(Integer, primary_key=True, index=True)
    tool_name = Column(String)
    payload = Column(JSON)
    status = Column(String) # 'approved', 'denied', 'executed'
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    phone = Column(String)


class LongTermMemory(Base):
    """Encrypted persistent memory that survives restarts."""
    __tablename__ = "long_term_memory"

    id = Column(Integer, primary_key=True, index=True)
    # category stored encrypted (e.g. 'coding', 'personal', 'companion')
    category = Column(Text, nullable=False)
    # full memory content — always encrypted
    content = Column(Text, nullable=False)
    # 1-5: 1=trivial, 3=normal, 5=critical. Unencrypted for fast filtering.
    importance = Column(Integer, default=3)
    # NULL means never expires (importance >= 4). Otherwise a UTC datetime.
    expires_at = Column(DateTime(timezone=True), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    source_session_id = Column(String, nullable=True)


class ScheduledTask(Base):
    """Background tasks that Maya runs on a schedule."""
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True)
    # Task name — encrypted
    name = Column(Text, nullable=False)
    # cron-like expression or ISO datetime string for one-shot reminders
    cron_expression = Column(String, nullable=True)
    # Whitelist: DAILY_GREETING | WEATHER_CHECK | REMINDER
    task_type = Column(String, nullable=False)
    # Encrypted JSON payload specific to task_type
    task_payload = Column(Text, nullable=True)
    is_active = Column(Integer, default=1)  # 1=active, 0=disabled
    last_run = Column(DateTime(timezone=True), nullable=True)
    next_run = Column(DateTime(timezone=True), nullable=True)
    # gui_popup = WebSocket toast to frontend; chat_message = Maya speaks it
    notify_channel = Column(String, default="chat_message")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
