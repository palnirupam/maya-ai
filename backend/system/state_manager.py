import logging
from typing import Set, Dict
from pydantic import BaseModel
from .event_bus import system_event_bus
from ..brain.personality.modes.registry import MODES, CAPABILITY_PROFILES

logger = logging.getLogger(__name__)

class AssistantState(BaseModel):
    active_mode: str = "companion"
    active_theme: str = "purple"
    capability_profile: str = "restricted_automation"
    capabilities: Set[str] = set(CAPABILITY_PROFILES["restricted_automation"])
    emotional_state: str = "focused"
    session_flags: Dict[str, str] = {}
    runtime_status: str = "awake"

class StateManager:
    """Single Source of Truth for Maya's runtime state."""
    
    def __init__(self):
        self.state = AssistantState()
        
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
        
        # Emit Event
        await system_event_bus.publish("MODE_CHANGED", {
            "mode": new_mode,
            "theme": mode_config["theme"],
            "capabilities": list(self.state.capabilities)
        })
        return True
        
    def get_prompt_context(self) -> dict:
        """Returns the context needed for the PromptBuilder."""
        mode_config = MODES.get(self.state.active_mode, MODES["companion"])
        
        # Load user toggles from database to align prompt capabilities
        caps = set(self.state.capabilities)
        try:
            from ..database.connection import SessionLocal
            from ..database.models import UserPreferences
            from ..database.crypto import crypto_manager
            
            db = SessionLocal()
            try:
                def _is_enabled(key: str) -> bool:
                    pref = db.query(UserPreferences).filter(UserPreferences.key == key).first()
                    if pref and pref.value:
                        try:
                            return crypto_manager.decrypt(pref.value) == "true"
                        except:
                            pass
                    return False
                
                if _is_enabled("PERM_BROWSER"):
                    caps.add("browser.automation")
                    caps.add("desktop.automation")
                if _is_enabled("PERM_FILESYSTEM"):
                    caps.add("filesystem.write")
                    caps.add("filesystem.read")
                if _is_enabled("PERM_TERMINAL"):
                    caps.add("terminal.execute")
                    caps.add("filesystem.write")
                if _is_enabled("PERM_SYSTEM"):
                    caps.add("system.control")
                    caps.add("desktop.automation")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error loading settings in StateManager: {e}")
            
        return {
            "tone": mode_config["tone"],
            "capabilities": list(caps),
            "mode_name": self.state.active_mode
        }

state_manager = StateManager()
