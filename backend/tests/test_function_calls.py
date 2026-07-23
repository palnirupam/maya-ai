import unittest
from unittest.mock import MagicMock, patch

from backend.brain.gemini.function_calls import get_maya_tools

class TestFunctionCalls(unittest.TestCase):
    def test_get_maya_tools(self):
        # Should not crash and should return a list of callable tools
        tools = get_maya_tools()
        self.assertTrue(len(tools) > 0)
        for tool in tools:
            self.assertTrue(callable(tool))

    def test_unreadable_permission_prefs_do_not_remove_core_agent_tools(self):
        pref = MagicMock()
        pref.key = "PERM_SYSTEM"
        pref.value = "encrypted-but-unreadable"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = pref

        with patch("backend.brain.gemini.function_calls.SessionLocal", return_value=db), \
             patch("backend.database.preferences.crypto_manager.decrypt", return_value=""):
            names = {getattr(t, "__name__", "") for t in get_maya_tools()}

        self.assertIn("whatsapp_send_message", names)
        self.assertIn("whatsapp_send_file", names)
        self.assertIn("read_whatsapp_chat", names)
        self.assertIn("pc", names)
        self.assertIn("file", names)
        self.assertIn("create_pdf", names)
        self.assertIn("web_search", names)
        self.assertNotIn("execute_python", names)  # terminal remains off by default

    def test_explicit_false_permission_pref_is_respected(self):
        pref = MagicMock()
        pref.key = "PERM_SYSTEM"
        pref.value = "encrypted-false"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = pref

        with patch("backend.brain.gemini.function_calls.SessionLocal", return_value=db), \
             patch("backend.database.preferences.crypto_manager.decrypt", return_value="false"):
            names = {getattr(t, "__name__", "") for t in get_maya_tools()}

        self.assertNotIn("whatsapp_send_message", names)
        self.assertNotIn("file", names)
        self.assertNotIn("create_pdf", names)
        self.assertNotIn("web_search", names)
        self.assertFalse(
            {
                "type_text", "press_key", "click_mouse", "open_app",
                "close_app", "close_apps_except", "manage_window",
                "look_at_screen", "take_verified_screenshot", "pc",
                "manage_processes", "background_app_control",
                "vision_guided_action", "get_app_text_content",
                "configure_mcp_server",
            }
            & names
        )

if __name__ == "__main__":
    unittest.main()
