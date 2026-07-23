from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    kind: str
    default_model: str
    api_url: str | None = None
    models_url: str | None = None
    fallback_models: tuple[str, ...] = ()
    requires_base_url: bool = False
    default_base_url: str = ""


DEFAULT_PROVIDER = "gemini"

ENV_PROVIDER_KEYS = ("MAYA_AI_PROVIDER", "GEMINI_API_PROVIDER")
ENV_MODEL_KEYS = ("MAYA_AI_MODEL", "GEMINI_ACTIVE_MODEL")
ENV_BASE_URL_KEYS = ("MAYA_AI_BASE_URL", "GEMINI_API_BASE_URL")

OPENAI_COMPATIBLE_KIND = "openai_compatible"
GEMINI_KIND = "gemini"
ANTHROPIC_KIND = "anthropic"


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        id="gemini",
        label="Google Gemini",
        kind=GEMINI_KIND,
        default_model="fast",
        fallback_models=(
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ),
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        label="OpenRouter",
        kind=OPENAI_COMPATIBLE_KIND,
        default_model="deepseek/deepseek-chat-v3-0324:free",
        api_url="https://openrouter.ai/api/v1/chat/completions",
        models_url="https://openrouter.ai/api/v1/models",
        fallback_models=(
            "deepseek/deepseek-chat-v3-0324:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "meta-llama/llama-3.2-3b-instruct:free",
        ),
    ),
    "nvidia": ProviderSpec(
        id="nvidia",
        label="NVIDIA NIM",
        kind=OPENAI_COMPATIBLE_KIND,
        default_model="meta/llama-3.3-70b-instruct",
        api_url="https://integrate.api.nvidia.com/v1/chat/completions",
        fallback_models=("meta/llama-3.1-8b-instruct",),
    ),
    "groq": ProviderSpec(
        id="groq",
        label="Groq",
        kind=OPENAI_COMPATIBLE_KIND,
        default_model="llama-3.3-70b-versatile",
        api_url="https://api.groq.com/openai/v1/chat/completions",
        fallback_models=(
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ),
    ),
    "opencode_zen": ProviderSpec(
        id="opencode_zen",
        label="OpenCode Zen",
        kind=OPENAI_COMPATIBLE_KIND,
        default_model="deepseek-v4-flash-free",
        api_url="https://opencode.ai/zen/v1/chat/completions",
        models_url="https://opencode.ai/zen/v1/models",
        fallback_models=(
            "nemotron-3-ultra-free",
            "nemotron-3-super-free",
            "mimo-v2.5-free",
            "minimax-m2.5-free",
            "qwen3.6-plus-free",
        ),
    ),
    "openai": ProviderSpec(
        id="openai",
        label="OpenAI",
        kind=OPENAI_COMPATIBLE_KIND,
        default_model="gpt-4o-mini",
        api_url="https://api.openai.com/v1/chat/completions",
        models_url="https://api.openai.com/v1/models",
    ),
    "cloudflare": ProviderSpec(
        id="cloudflare",
        label="Cloudflare Workers AI",
        kind=OPENAI_COMPATIBLE_KIND,
        default_model="@cf/meta/llama-3.1-8b-instruct",
        requires_base_url=True,
    ),
    "custom_openai": ProviderSpec(
        id="custom_openai",
        label="Custom OpenAI-compatible",
        kind=OPENAI_COMPATIBLE_KIND,
        default_model="gpt-4o-mini",
        requires_base_url=True,
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        label="Claude API",
        kind=ANTHROPIC_KIND,
        default_model="claude-3-5-haiku-latest",
        api_url="https://api.anthropic.com/v1/messages",
    ),
}


ALIASES = {
    "auto": "",
    "google": "gemini",
    "google_gemini": "gemini",
    "claude": "anthropic",
    "claudeapi": "anthropic",
    "claude_api": "anthropic",
    "anthropic_claude": "anthropic",
    "zen": "opencode_zen",
    "opencode": "opencode_zen",
    "nvdia": "nvidia",
    "cf": "cloudflare",
    "workers_ai": "cloudflare",
    "openai_compatible": "custom_openai",
    "custom": "custom_openai",
}


def normalize_provider(provider: str | None) -> str:
    raw = (provider or "").strip().lower().replace("-", "_")
    raw = ALIASES.get(raw, raw)
    if raw in PROVIDER_SPECS:
        return raw
    return DEFAULT_PROVIDER


def _first_env(keys: tuple[str, ...]) -> str:
    for key in keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return ""


def provider_from_env() -> str:
    value = _first_env(ENV_PROVIDER_KEYS)
    return normalize_provider(value) if value else ""


def model_from_env() -> str:
    return _first_env(ENV_MODEL_KEYS)


def base_url_from_env() -> str:
    return _first_env(ENV_BASE_URL_KEYS)


def _provider_from_key_prefix(key: str) -> str:
    clean = (key or "").strip()
    if clean.startswith("sk-or-"):
        return "openrouter"
    if clean.startswith("nvapi-"):
        return "nvidia"
    if clean.startswith("gsk_"):
        return "groq"
    if clean.startswith("sk-ant-"):
        return "anthropic"
    if clean.startswith("sk-"):
        return "opencode_zen" if len(clean) == 67 else "openai"
    return DEFAULT_PROVIDER


def detect_provider_from_key(key: str, preferred: str | None = None) -> str:
    inferred = _provider_from_key_prefix(key)
    raw_preferred = (preferred or "").strip().lower().replace("-", "_")
    raw_preferred = ALIASES.get(raw_preferred, raw_preferred)
    explicit = raw_preferred if raw_preferred in PROVIDER_SPECS else ""

    # A saved/default Gemini selection should not force a new OpenAI-compatible
    # key down the Gemini path. Non-Gemini explicit selections are respected
    # because providers like Cloudflare cannot be inferred from token prefix.
    if explicit and explicit != DEFAULT_PROVIDER:
        return explicit
    if inferred != DEFAULT_PROVIDER:
        return inferred
    return explicit or DEFAULT_PROVIDER


def provider_spec(provider: str | None) -> ProviderSpec:
    return PROVIDER_SPECS[normalize_provider(provider)]


def provider_options(resolve_gemini_tier: Callable[[str], str] | None = None) -> list[dict]:
    return [
        {
            "id": spec.id,
            "label": spec.label,
            "kind": spec.kind,
            "default_model": model_for_provider(spec.id, None, resolve_gemini_tier),
            "requires_base_url": spec.requires_base_url,
        }
        for spec in PROVIDER_SPECS.values()
    ]


def normalize_openai_base_url(base_url: str | None) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def chat_url_for_provider(provider: str | None, base_url: str | None = None) -> str:
    spec = provider_spec(provider)
    if spec.requires_base_url:
        return normalize_openai_base_url(base_url)
    return spec.api_url or ""


def fallback_models_for_provider(provider: str | None) -> list[str]:
    spec = provider_spec(provider)
    return list(spec.fallback_models)


def is_model_compatible(provider: str | None, model: str | None) -> bool:
    provider_id = normalize_provider(provider)
    model_value = (model or "").strip()
    if not model_value:
        return False
    if provider_id == "gemini":
        return model_value in {"fast", "reasoning", "thinking"} or model_value.startswith("gemini-")
    if provider_id == "openrouter":
        return True
    if provider_id == "cloudflare":
        return model_value.startswith("@cf/")
    if provider_id == "anthropic":
        return model_value.startswith("claude-")
    return not (model_value.startswith("gemini-") or model_value.startswith("google/"))


def model_for_provider(
    provider: str | None,
    stored_model: str | None,
    resolve_gemini_tier: Callable[[str], str] | None = None,
) -> str:
    provider_id = normalize_provider(provider)
    spec = provider_spec(provider_id)
    model = (stored_model or "").strip()
    default_model = spec.default_model

    if provider_id == "gemini":
        resolver = resolve_gemini_tier or (lambda tier: tier)
        if model in {"fast", "reasoning", "thinking"}:
            return resolver(model)
        if not model:
            return resolver(default_model)
        return model if is_model_compatible(provider_id, model) else resolver(default_model)

    if not model:
        return default_model
    return model if is_model_compatible(provider_id, model) else default_model
