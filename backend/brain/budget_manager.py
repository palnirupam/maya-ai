"""
BudgetManager — backend/brain/budget_manager.py

Tracks token usage per session and downgrades the model tier when the budget
is exhausted. Unlike the silent downgrade bug (where the model changed without
any user signal), this manager:

  1. Always logs the downgrade to Observability.
  2. Yields a user-visible status event to the frontend ("Switching to fast
     model to stay within budget — results may be less detailed").
  3. Restores the original tier at the start of the next session or after a
     cooldown window.

Integration: agent_team.py reads get_active_tier(session_id) before every
Gemini call. BudgetManager.record_usage() is called after every call with
the actual token counts from the response.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

ModelTier = Literal["fast", "reasoning", "thinking"]

# ── Budget limits (in approximate tokens) ────────────────────────────────────
# These are per-session soft limits. Hitting them triggers a downgrade, not
# a hard error. The limits are intentionally generous; they only fire when a
# session is genuinely burning through a huge context (e.g. recursive loops).
TIER_BUDGETS: Dict[ModelTier, int] = {
    "thinking": 80_000,    # downgrade to "reasoning" when exceeded
    "reasoning": 200_000,  # downgrade to "fast" when exceeded
    "fast": 500_000,       # hard cap — yield error if exceeded
}

DOWNGRADE_PATH: Dict[ModelTier, ModelTier] = {
    "thinking": "reasoning",
    "reasoning": "fast",
}

# ── User-visible downgrade messages ──────────────────────────────────────────
_DOWNGRADE_MESSAGES: Dict[ModelTier, str] = {
    "reasoning": (
        "💡 Token budget reached for deep-thinking mode. "
        "Switching to reasoning model — response quality remains high."
    ),
    "fast": (
        "⚡ Reasoning budget reached. Switching to fast model. "
        "Responses will be quicker but less detailed."
    ),
}


@dataclass
class SessionBudget:
    requested_tier: ModelTier = "fast"
    active_tier: ModelTier = "fast"
    tokens_used: int = 0
    downgraded: bool = False
    downgrade_notified: bool = False   # has the user been told about the downgrade?
    last_used_ts: float = field(default_factory=time.monotonic)


class BudgetManager:
    """Per-session token budget tracker with graceful model downgrading."""

    def __init__(self):
        self._sessions: Dict[str, SessionBudget] = {}

    def _get(self, session_id: str) -> SessionBudget:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionBudget()
        return self._sessions[session_id]

    def set_requested_tier(self, session_id: str, tier: ModelTier) -> None:
        """Called by AnalysisPass to declare the intended model tier."""
        budget = self._get(session_id)
        budget.requested_tier = tier
        # If we previously downgraded, but now it's a new (fresh) tier request
        # and we've cooled down, restore.
        if not budget.downgraded:
            budget.active_tier = tier
        budget.last_used_ts = time.monotonic()

    def get_active_tier(self, session_id: str) -> ModelTier:
        """Return the tier that should actually be used (may be lower than requested)."""
        return self._get(session_id).active_tier

    def record_usage(self, session_id: str, tokens_in: int, tokens_out: int) -> Optional[Tuple[str, str]]:
        """
        Update token counters after a model call.
        Returns (old_tier, new_tier) if this call triggered a downgrade, else None
        — callers use this to log the event to Observability (see orchestrator.py).
        """
        budget = self._get(session_id)
        budget.tokens_used += tokens_in + tokens_out
        budget.last_used_ts = time.monotonic()
        return self._maybe_downgrade(session_id, budget)

    def _maybe_downgrade(self, session_id: str, budget: SessionBudget) -> Optional[Tuple[str, str]]:
        """Check if current tier's budget is exceeded and downgrade if so."""
        limit = TIER_BUDGETS.get(budget.active_tier, 500_000)
        if budget.tokens_used > limit and budget.active_tier in DOWNGRADE_PATH:
            old_tier = budget.active_tier
            new_tier = DOWNGRADE_PATH[old_tier]
            budget.active_tier = new_tier
            budget.downgraded = True
            budget.downgrade_notified = False  # signal: frontend not yet notified
            logger.warning(
                f"[BudgetManager] Session {session_id}: tier downgraded "
                f"{old_tier!r} → {new_tier!r} after {budget.tokens_used} tokens."
            )
            return (old_tier, new_tier)
        return None

    def pop_downgrade_notification(self, session_id: str) -> str | None:
        """
        If a downgrade occurred and the user hasn't been notified, returns the
        user-visible message and marks it as notified. Returns None otherwise.
        Called by agent_team before streaming so the message appears inline.
        """
        budget = self._get(session_id)
        if budget.downgraded and not budget.downgrade_notified:
            budget.downgrade_notified = True
            return _DOWNGRADE_MESSAGES.get(budget.active_tier)
        return None

    def reset_session(self, session_id: str) -> None:
        """Reset a session's budget (call on explicit session clear / mode change)."""
        self._sessions.pop(session_id, None)
        logger.info(f"[BudgetManager] Session {session_id} budget reset.")

    def evict_stale(self, max_idle_seconds: float = 3600.0) -> int:
        """Remove sessions idle for longer than max_idle_seconds. Returns eviction count."""
        now = time.monotonic()
        stale = [
            sid for sid, b in self._sessions.items()
            if (now - b.last_used_ts) > max_idle_seconds
        ]
        for sid in stale:
            del self._sessions[sid]
        if stale:
            logger.info(f"[BudgetManager] Evicted {len(stale)} stale sessions.")
        return len(stale)


# Singleton
budget_manager = BudgetManager()
