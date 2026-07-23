import os
import yaml
from pathlib import Path
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "models.yaml"

@dataclass
class ModelsConfig:
    fast: str
    reasoning: str
    thinking: str
    embedding_cloud: str
    embedding_local: str

@dataclass
class ThresholdsConfig:
    fast_max_score: int
    reasoning_max_score: int
    thinking_min_score: int

@dataclass
class MayaConfig:
    models: ModelsConfig
    thresholds: ThresholdsConfig

def _resolve_env_var(value: str) -> str:
    """Resolves strings like '${MAYA_MODEL_FAST:-gemini-3.5-flash}'"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        content = value[2:-1]
        if ":-" in content:
            env_name, default_val = content.split(":-", 1)
        else:
            env_name, default_val = content, ""
        return os.environ.get(env_name, default_val)
    return value

def load_config() -> MayaConfig:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
            
        models_raw = raw.get("models", {})
        models = ModelsConfig(
            fast=_resolve_env_var(models_raw.get("fast", "gemini-3.5-flash")),
            reasoning=_resolve_env_var(models_raw.get("reasoning", "gemini-3.1-pro")),
            thinking=_resolve_env_var(models_raw.get("thinking", "gemini-3.1-pro")),
            embedding_cloud=_resolve_env_var(models_raw.get("embedding_cloud", "gemini-embedding-2")),
            embedding_local=_resolve_env_var(models_raw.get("embedding_local", ""))
        )
        
        thresholds_raw = raw.get("thresholds", {})
        thresholds = ThresholdsConfig(
            fast_max_score=int(thresholds_raw.get("fast_max_score", 2)),
            reasoning_max_score=int(thresholds_raw.get("reasoning_max_score", 6)),
            thinking_min_score=int(thresholds_raw.get("thinking_min_score", 7))
        )
        
        return MayaConfig(models=models, thresholds=thresholds)
    except Exception as e:
        logger.error(f"Failed to load models.yaml, using defaults: {e}")
        # Fallback defaults
        return MayaConfig(
            models=ModelsConfig(
                fast="gemini-3.5-flash",
                reasoning="gemini-3.1-pro",
                thinking="gemini-3.1-pro",
                embedding_cloud="gemini-embedding-2",
                embedding_local=""
            ),
            thresholds=ThresholdsConfig(2, 6, 7)
        )

maya_config = load_config()

_VALID_TIERS = {"fast", "reasoning", "thinking", "embedding_cloud", "embedding_local"}

def get_model(tier: str) -> str:
    """Returns the model string for a given tier.
    
    Valid tiers: 'fast', 'reasoning', 'thinking', 'embedding_cloud', 'embedding_local'.
    Raises ValueError for unknown tiers to prevent silent misconfiguration.
    Returns empty string for 'embedding_local' when not configured (callers must handle).
    """
    if tier not in _VALID_TIERS:
        raise ValueError(f"Unknown model tier: {tier!r}. Valid: {_VALID_TIERS}")
    return getattr(maya_config.models, tier, "")


def reload_config() -> MayaConfig:
    """Force re-read of models.yaml. Call this after env var changes or hot reloads."""
    global maya_config
    maya_config = load_config()
    logger.info("model_config: reloaded from disk.")
    return maya_config
