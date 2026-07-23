import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("."))

from backend.brain.providers.gemini_adapter import (
    _model_for_provider,
    convert_context_to_anthropic_messages,
    convert_tools_to_anthropic_tools,
)
from backend.config.provider_config import (
    base_url_from_env,
    chat_url_for_provider,
    detect_provider_from_key,
    fallback_models_for_provider,
    model_from_env,
    provider_from_env,
)


class TestProviderDetection(unittest.TestCase):
    def test_non_gemini_key_prefix_overrides_saved_gemini_default(self):
        self.assertEqual(detect_provider_from_key("sk-ant-test", "gemini"), "anthropic")
        self.assertEqual(detect_provider_from_key("nvapi-test", "gemini"), "nvidia")
        self.assertEqual(detect_provider_from_key("sk-or-test", "gemini"), "openrouter")

    def test_explicit_provider_is_respected_for_opaque_keys(self):
        self.assertEqual(detect_provider_from_key("opaque-token", "cloudflare"), "cloudflare")
        self.assertEqual(detect_provider_from_key("opaque-token", "custom_openai"), "custom_openai")

    def test_common_aliases_are_normalized(self):
        self.assertEqual(detect_provider_from_key("opaque-token", "claudeapi"), "anthropic")
        self.assertEqual(detect_provider_from_key("opaque-token", "nvdia"), "nvidia")

    def test_provider_can_be_forced_from_environment(self):
        old_provider = os.environ.get("GEMINI_API_PROVIDER")
        old_maya_provider = os.environ.get("MAYA_AI_PROVIDER")
        old_model = os.environ.get("GEMINI_ACTIVE_MODEL")
        old_base_url = os.environ.get("MAYA_AI_BASE_URL")
        try:
            os.environ.pop("MAYA_AI_PROVIDER", None)
            os.environ["GEMINI_API_PROVIDER"] = "openrouter"
            os.environ["GEMINI_ACTIVE_MODEL"] = "deepseek/deepseek-chat-v3-0324:free"
            os.environ["MAYA_AI_BASE_URL"] = "https://example.test/v1"

            self.assertEqual(provider_from_env(), "openrouter")
            self.assertEqual(model_from_env(), "deepseek/deepseek-chat-v3-0324:free")
            self.assertEqual(base_url_from_env(), "https://example.test/v1")
        finally:
            for key, value in {
                "GEMINI_API_PROVIDER": old_provider,
                "MAYA_AI_PROVIDER": old_maya_provider,
                "GEMINI_ACTIVE_MODEL": old_model,
                "MAYA_AI_BASE_URL": old_base_url,
            }.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class TestProviderUrlsAndModels(unittest.TestCase):
    def test_cloudflare_base_url_gets_openai_chat_suffix(self):
        self.assertEqual(
            chat_url_for_provider(
                "cloudflare",
                "https://api.cloudflare.com/client/v4/accounts/abc/ai",
            ),
            "https://api.cloudflare.com/client/v4/accounts/abc/ai/v1/chat/completions",
        )

    def test_existing_openai_chat_url_is_left_intact(self):
        self.assertEqual(
            chat_url_for_provider("custom_openai", "https://example.com/v1/chat/completions"),
            "https://example.com/v1/chat/completions",
        )

    def test_anthropic_rejects_gemini_model_and_uses_default(self):
        self.assertEqual(_model_for_provider("anthropic", "gemini-3.5-flash"), "claude-3-5-haiku-latest")

    def test_zen_fallbacks_include_extra_free_models(self):
        self.assertEqual(fallback_models_for_provider("opencode_zen"), [
            "nemotron-3-ultra-free",
            "nemotron-3-super-free",
            "mimo-v2.5-free",
            "minimax-m2.5-free",
            "qwen3.6-plus-free",
        ])


class TestAnthropicConversion(unittest.TestCase):
    def test_tool_schema_conversion(self):
        tools = [{
            "type": "function",
            "function": {
                "name": "file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"src": {"type": "string"}},
                    "required": ["src"],
                },
            },
        }]

        self.assertEqual(convert_tools_to_anthropic_tools(tools), [{
            "name": "file",
            "description": "Read a file",
            "input_schema": {
                "type": "object",
                "properties": {"src": {"type": "string"}},
                "required": ["src"],
            },
        }])

    def test_context_conversion_preserves_system_user_and_tool_flow(self):
        context = [
            {"role": "system", "content": "You are Maya."},
            {"role": "user", "content": "read file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "file", "arguments": "{\"src\":\"a.txt\"}"},
                }],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "hello"},
        ]

        system, messages = convert_context_to_anthropic_messages(context)

        self.assertEqual(system, "You are Maya.")
        self.assertEqual(messages[0], {"role": "user", "content": "read file"})
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"][0]["type"], "tool_use")
        self.assertEqual(messages[1]["content"][0]["name"], "file")
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual(messages[2]["content"][0]["type"], "tool_result")
        self.assertEqual(messages[2]["content"][0]["tool_use_id"], "call_1")


if __name__ == "__main__":
    unittest.main()
