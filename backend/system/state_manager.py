import logging
from typing import Set, Dict
from pydantic import BaseModel
from .event_bus import system_event_bus
from ..brain.personality.modes.registry import MODES, CAPABILITY_PROFILES

logger = logging.getLogger(__name__)

class AssistantState(BaseModel):
    active_mode: str = "professional"
    active_theme: str = "purple"
    capability_profile: str = "full_automation"
    capabilities: Set[str] = set(CAPABILITY_PROFILES["full_automation"])
    emotional_state: str = "focused"
    session_flags: Dict[str, str] = {}
    runtime_status: str = "awake"

class StateManager:
    """Single Source of Truth for Maya's runtime state."""
    
    def __init__(self):
        self.state = AssistantState()
        self._permissions_cache: set[str] | None = None

    def invalidate_permissions(self) -> None:
        """Invalidates the permission capabilities cache so next turn reloads from DB."""
        self._permissions_cache = None

    async def change_mode(self, new_mode: str) -> bool:
        """Validates and applies a mode transition."""
        if new_mode not in MODES:
            logger.error(f"Invalid mode requested: {new_mode}")
            return False

        mode_config = MODES[new_mode]
        cap_profile = mode_config["capability_profile"]

        # State Update
        self.state.active_mode = new_mode
        self.state.active_theme = mode_config["theme"]
        self.state.capability_profile = cap_profile
        self.state.capabilities = set(CAPABILITY_PROFILES.get(cap_profile, []))

        logger.info(f"[StateManager] Mode changed to '{new_mode}' | Capabilities: {self.state.capabilities}")

        # Mark active sessions dirty so new personality system prompt applies on next turn
        try:
            from ..brain.orchestrator import orchestrator
            try:
                from ..brain.budget_manager import budget_manager
                for sid in list(orchestrator.sessions.keys()):
                    budget_manager.reset_session(sid)
                logger.info("[StateManager] BudgetManager sessions reset on mode change.")
            except Exception as be:
                logger.warning(f"[StateManager] Could not reset BudgetManager: {be}")
            orchestrator.mark_sessions_dirty()
            logger.info(f"[StateManager] All active sessions marked dirty — new personality active.")
        except Exception as e:
            logger.warning(f"[StateManager] Could not mark sessions dirty: {e}")

        # Emit Event
        await system_event_bus.publish("MODE_CHANGED", {
            "mode": new_mode,
            "theme": mode_config["theme"],
            "capabilities": list(self.state.capabilities)
        })
        return True

    def load_permissions(self) -> set[str]:
        """Loads user permission toggles from DB and returns capability set."""
        if self._permissions_cache is not None:
            return set(self._permissions_cache)

        granted_caps: set[str] = set()
        try:
            from ..database.connection import SessionLocal
            from ..database.preferences import read_permission_pref

            db = SessionLocal()
            try:
                if read_permission_pref(db, "PERM_BROWSER"):
                    granted_caps.add("browser.automation")
                    granted_caps.add("desktop.automation")
                if read_permission_pref(db, "PERM_FILESYSTEM"):
                    granted_caps.add("filesystem.write")
                    granted_caps.add("filesystem.read")
                if read_permission_pref(db, "PERM_TERMINAL"):
                    granted_caps.add("terminal.execute")
                    granted_caps.add("filesystem.write")
                if read_permission_pref(db, "PERM_SYSTEM"):
                    granted_caps.add("system.control")
                    granted_caps.add("desktop.automation")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error loading settings in StateManager: {e}")

        self._permissions_cache = granted_caps
        return set(granted_caps)

    def get_prompt_context(self) -> dict:
        """Returns the context needed for the PromptBuilder (0 DB queries when cached)."""
        mode_config = MODES.get(self.state.active_mode, MODES["professional"])
        caps = set(self.state.capabilities) | self.load_permissions()

        return {
            "tone": mode_config["tone"],
            "capabilities": list(caps),
            "mode_name": self.state.active_mode
        }


state_manager = StateManager()
