import time
import logging

logger = logging.getLogger(__name__)

import time
import logging
import asyncio

logger = logging.getLogger(__name__)

class CooldownManager:
    """
    Tracks failing LLM models/providers and places them in a cooldown state.
    This prevents the system from wasting latency on models that are currently 
    returning 503, 429, or timing out.
    
    Now supports active health probing with exponential backoff for transient errors
    while bypassing probing for authentication/authorization errors.
    """
    def __init__(self, default_cooldown_sec: int = 600):
        self._cooldowns: dict[str, float] = {}
        self.default_cooldown_sec = default_cooldown_sec
        self._backoffs: dict[str, int] = {}  # model_name -> current_backoff_index
        self._probe_next_time: dict[str, float] = {}  # model_name -> timestamp of next probe
        self._non_probables: set[str] = set()  # models with permanent auth errors
        self._probe_callback = None  # async def (model_name) -> bool
        self._probing_task: asyncio.Task | None = None

    def register_probe_callback(self, callback):
        """Registers the async callback used to probe a model's health."""
        self._probe_callback = callback
        # If there are already models needing probe, start loop
        if self._probe_next_time:
            self._ensure_probing_loop()

    def mark_failed(self, model_name: str, reason: str = "Unknown Error"):
        """Marks a model as failed and places it in cooldown."""
        resume_time = time.time() + self.default_cooldown_sec
        self._cooldowns[model_name] = resume_time
        
        reason_lower = reason.lower()
        is_auth_error = any(x in reason_lower for x in [
            "401", "403", "unauthorized", "forbidden", "api key", "invalid key", 
            "credential", "api_key_invalid", "api-key"
        ])
        
        if is_auth_error:
            self._non_probables.add(model_name)
            if model_name in self._backoffs:
                del self._backoffs[model_name]
            if model_name in self._probe_next_time:
                del self._probe_next_time[model_name]
            logger.warning(
                f"[Fallback] Model '{model_name}' marked as FAILED with AUTH ERROR ({reason}). "
                f"Probing skipped. Cooldown until {resume_time}."
            )
        else:
            if model_name in self._non_probables:
                self._non_probables.remove(model_name)
            
            # Initialize/progress backoff index
            backoff_intervals = [30, 60, 120, 300]
            if model_name not in self._backoffs:
                self._backoffs[model_name] = 0
            else:
                self._backoffs[model_name] = min(self._backoffs[model_name] + 1, len(backoff_intervals) - 1)
            
            idx = self._backoffs[model_name]
            delay = backoff_intervals[idx]
            self._probe_next_time[model_name] = time.time() + delay
            
            logger.warning(
                f"[Fallback] Model '{model_name}' marked as FAILED ({reason}). "
                f"Probing scheduled in {delay}s (backoff index {idx}). Cooldown until {resume_time}."
            )
            self._ensure_probing_loop()

    def mark_success(self, model_name: str):
        """Clears the cooldown for a model if it succeeds."""
        if model_name in self._cooldowns:
            del self._cooldowns[model_name]
        if model_name in self._backoffs:
            del self._backoffs[model_name]
        if model_name in self._probe_next_time:
            del self._probe_next_time[model_name]
        if model_name in self._non_probables:
            self._non_probables.remove(model_name)
        logger.info(f"[Fallback] Model '{model_name}' has recovered. Cooldown and probing cleared.")

    def clear_all(self):
        """Clears all states (cooldowns, backoffs, non-probables) on key reload."""
        self._cooldowns.clear()
        self._backoffs.clear()
        self._probe_next_time.clear()
        self._non_probables.clear()
        logger.info("[Fallback] All model cooldowns, backoffs, and non-probables cleared.")

    def is_in_cooldown(self, model_name: str) -> bool:
        """Checks if a model is currently in cooldown."""
        if model_name not in self._cooldowns:
            return False
            
        if time.time() > self._cooldowns[model_name]:
            # Cooldown expired
            self.mark_success(model_name)
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

    def _ensure_probing_loop(self):
        """Starts the background probing task if not already running."""
        if self._probing_task is None or self._probing_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._probing_task = loop.create_task(self._probing_loop())
                logger.info("[Fallback] Background probing loop started.")
            except RuntimeError:
                # No running event loop (e.g. during startup or unit testing if not run in loop)
                pass

    async def _probing_loop(self):
        """Asynchronously probes failing models with backoff intervals."""
        backoff_intervals = [30, 60, 120, 300]
        while True:
            models_to_probe = list(self._probe_next_time.keys())
            if not models_to_probe:
                await asyncio.sleep(5)
                if not self._probe_next_time:
                    break
                continue
                
            now = time.time()
            for model in models_to_probe:
                if model not in self._probe_next_time:
                    continue
                if now >= self._probe_next_time[model]:
                    if not self._probe_callback:
                        logger.warning(f"[Fallback] No probe callback registered. Skipping probe for '{model}'.")
                        self._probe_next_time[model] = now + 30
                        continue
                    
                    logger.info(f"[Fallback] Probing model '{model}' for recovery...")
                    try:
                        success = await self._probe_callback(model)
                    except Exception as e:
                        logger.error(f"[Fallback] Exception in probe callback for '{model}': {e}")
                        success = False
                        
                    if success:
                        logger.info(f"[Fallback] Model '{model}' successfully probed. Restoring.")
                        self.mark_success(model)
                    else:
                        # Increment backoff
                        idx = self._backoffs.get(model, 0)
                        next_idx = min(idx + 1, len(backoff_intervals) - 1)
                        self._backoffs[model] = next_idx
                        delay = backoff_intervals[next_idx]
                        self._probe_next_time[model] = time.time() + delay
                        logger.warning(
                            f"[Fallback] Probe failed for model '{model}'. "
                            f"Next probe scheduled in {delay}s (backoff index {next_idx})."
                        )
            await asyncio.sleep(5)
        self._probing_task = None
        logger.info("[Fallback] Background probing loop stopped.")

fallback_manager = CooldownManager()
