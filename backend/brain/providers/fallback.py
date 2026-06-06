import time
import logging

logger = logging.getLogger(__name__)

class CooldownManager:
    """
    Tracks failing LLM models/providers and places them in a cooldown state.
    This prevents the system from wasting latency on models that are currently 
    returning 503, 429, or timing out.
    """
    def __init__(self, default_cooldown_sec: int = 600):
        self._cooldowns: dict[str, float] = {}
        self.default_cooldown_sec = default_cooldown_sec

    def mark_failed(self, model_name: str, reason: str = "Unknown Error"):
        """Marks a model as failed and places it in cooldown."""
        resume_time = time.time() + self.default_cooldown_sec
        self._cooldowns[model_name] = resume_time
        logger.warning(f"[Fallback] Model '{model_name}' marked as FAILED ({reason}). Cooldown until {resume_time}.")

    def mark_success(self, model_name: str):
        """Clears the cooldown for a model if it succeeds."""
        if model_name in self._cooldowns:
            del self._cooldowns[model_name]
            logger.info(f"[Fallback] Model '{model_name}' has recovered. Cooldown cleared.")

    def is_in_cooldown(self, model_name: str) -> bool:
        """Checks if a model is currently in cooldown."""
        if model_name not in self._cooldowns:
            return False
            
        if time.time() > self._cooldowns[model_name]:
            # Cooldown expired
            del self._cooldowns[model_name]
            logger.info(f"[Fallback] Cooldown expired for '{model_name}'. Will retry.")
            return False
            
        return True

    def get_available_models(self, models_to_try: list[str]) -> list[str]:
        """Filters a list of models, returning only those not in cooldown."""
        available = [m for m in models_to_try if not self.is_in_cooldown(m)]
        if not available:
            # If all are in cooldown, we have no choice but to try them all again 
            # (or at least the first one) to see if they've recovered early.
            logger.error("[Fallback] All models are in cooldown! Forcing retry of the primary model.")
            return models_to_try[:1]
        return available

fallback_manager = CooldownManager()
