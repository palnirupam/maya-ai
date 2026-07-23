"""Regression tests for wiring AnalysisPass/BudgetManager's per-message
model_tier into the actual Gemini model that answers a request.

Bug: run_heuristic_pass() computed a model_tier (fast/reasoning/thinking)
every turn, and BudgetManager could track/downgrade it, but self.model_name
on GeminiAdapter was only ever set once (at process start / on a Settings
save via reload_key()) and generate_response()/generate_stream() had no
per-call tier override at all — so the tier was computed, logged, and
completely ignored by model selection. See conversation history for the
full bug-hunt writeup.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest

from backend.brain.providers.gemini_adapter import GeminiAdapter, _model_for_provider
from backend.config.model_config import get_model


def _bare_adapter(api_provider: str, model_is_pinned: bool, model_name: str) -> GeminiAdapter:
    """Builds a GeminiAdapter without running reload_key() (which needs a
    real DB session and API key) — just enough state to exercise
    _resolve_primary_model()."""
    adapter = GeminiAdapter.__new__(GeminiAdapter)
    adapter.api_provider = api_provider
    adapter.model_is_pinned = model_is_pinned
    adapter.model_name = model_name
    return adapter


class TestTierResolutionWhenAuto(unittest.TestCase):
    """When the user has left the model as "auto" (not pinned), a per-call
    model_tier should genuinely pick the model instead of always falling
    back to the frozen self.model_name."""

    def test_thinking_tier_resolves_to_thinking_model(self):
        adapter = _bare_adapter("gemini", model_is_pinned=False, model_name=get_model("fast"))
        resolved = adapter._resolve_primary_model("thinking")
        self.assertEqual(resolved, get_model("thinking"))

    def test_reasoning_tier_resolves_to_reasoning_model(self):
        adapter = _bare_adapter("gemini", model_is_pinned=False, model_name=get_model("fast"))
        resolved = adapter._resolve_primary_model("reasoning")
        self.assertEqual(resolved, get_model("reasoning"))

    def test_fast_tier_resolves_to_fast_model(self):
        adapter = _bare_adapter("gemini", model_is_pinned=False, model_name=get_model("thinking"))
        resolved = adapter._resolve_primary_model("fast")
        self.assertEqual(resolved, get_model("fast"))

    def test_no_tier_falls_back_to_model_name(self):
        adapter = _bare_adapter("gemini", model_is_pinned=False, model_name=get_model("fast"))
        resolved = adapter._resolve_primary_model(None)
        self.assertEqual(resolved, adapter.model_name)


class TestPinnedModelOverridesTier(unittest.TestCase):
    """A user who has explicitly pinned a concrete model in Settings must
    always get that model — tier is never allowed to override an explicit
    choice."""

    def test_pinned_model_ignores_thinking_tier(self):
        adapter = _bare_adapter("gemini", model_is_pinned=True, model_name="gemini-3.1-pro-custom-pin")
        resolved = adapter._resolve_primary_model("thinking")
        self.assertEqual(resolved, "gemini-3.1-pro-custom-pin")

    def test_pinned_model_ignores_fast_tier(self):
        adapter = _bare_adapter("gemini", model_is_pinned=True, model_name="gemini-3.1-pro-custom-pin")
        resolved = adapter._resolve_primary_model("fast")
        self.assertEqual(resolved, "gemini-3.1-pro-custom-pin")


class TestNonGeminiProviderIgnoresTier(unittest.TestCase):
    """Tiers are only defined for the native Gemini provider in models.yaml —
    a model_tier passed for any other provider must be a harmless no-op."""

    def test_openrouter_ignores_tier(self):
        adapter = _bare_adapter("openrouter", model_is_pinned=False, model_name="deepseek/deepseek-chat-v3-0324:free")
        resolved = adapter._resolve_primary_model("thinking")
        self.assertEqual(resolved, "deepseek/deepseek-chat-v3-0324:free")


class TestModelForProviderTierLiterals(unittest.TestCase):
    """Sanity check that the three tier literals genuinely resolve to
    distinct-enough model strings via the existing resolver."""

    def test_fast_and_thinking_are_resolved_independently(self):
        self.assertEqual(_model_for_provider("gemini", "fast"), get_model("fast"))
        self.assertEqual(_model_for_provider("gemini", "thinking"), get_model("thinking"))


if __name__ == "__main__":
    unittest.main()
