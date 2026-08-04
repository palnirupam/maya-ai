"""Unit tests for the deterministic (zero-LLM) OS control parser.

intent_parsing is a leaf module (imports only ``re``), so these tests are
hermetic — no network, no heavy agent/provider/tool imports.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest

from backend.brain.agents.intent_parsing import (
    _parse_direct_os_action,
    _format_direct_os_response,
    _extract_os_level,
)


class TestParseDirectOsAction(unittest.TestCase):
    def test_volume_set(self):
        for text in ("volume 20 koro", "sound 55", "volume 0"):
            func, kwargs, ctrl, _ = _parse_direct_os_action(text)
            self.assertEqual(func, "change_volume")
            self.assertEqual(ctrl, "volume")
            self.assertIn("level", kwargs)

    def test_brightness_set_and_direction(self):
        func, kwargs, ctrl, _ = _parse_direct_os_action("brightness 60 koro")
        self.assertEqual((func, kwargs, ctrl), ("control_brightness", {"direction": "60"}, "brightness"))
        func, kwargs, _, _ = _parse_direct_os_action("brightness barao")
        self.assertEqual(kwargs, {"direction": "up"})
        func, kwargs, _, _ = _parse_direct_os_action("brightness kom koro")
        self.assertEqual(kwargs, {"direction": "down"})

    def test_mute_toggle(self):
        func, kwargs, ctrl, _ = _parse_direct_os_action("mute koro")
        self.assertEqual((func, kwargs), ("perform_shortcut", {"action": "mute"}))
        # "volume off" should map to mute, not change_volume
        self.assertEqual(_parse_direct_os_action("volume off")[0], "perform_shortcut")

    def test_clipboard_read(self):
        func, kwargs, _, _ = _parse_direct_os_action("clipboard e ki ache")
        self.assertEqual((func, kwargs), ("read_clipboard", {}))
        # bare "clipboard" with no read intent → not a deterministic action
        self.assertIsNone(_parse_direct_os_action("clipboard"))

    def test_named_levels(self):
        # "full" / "low" / "half" resolve to absolute percentages (the exact
        # cases that failed in the live Telegram log).
        self.assertEqual(_parse_direct_os_action("Volume full koro")[1], {"level": 100})
        self.assertEqual(_parse_direct_os_action("volume half koro")[1], {"level": 50})
        self.assertEqual(_parse_direct_os_action("Brightness low koro")[1], {"direction": "25"})
        self.assertEqual(_parse_direct_os_action("brightness full koro")[1], {"direction": "100"})
        self.assertEqual(_parse_direct_os_action("Laptop er brightness full koro")[0], "control_brightness")
        # named follow-up continuing the last control
        self.assertEqual(_parse_direct_os_action("full koro", "volume")[1], {"level": 100})

    def test_bare_followup_uses_last_control(self):
        # "50% koro" means volume or brightness depending on the last control.
        self.assertEqual(_parse_direct_os_action("50% koro", "volume")[0], "change_volume")
        self.assertEqual(_parse_direct_os_action("70 koro", "brightness")[0], "control_brightness")
        # …but a bare value with NO prior control is ambiguous → None.
        self.assertIsNone(_parse_direct_os_action("50% koro", None))

    def test_bluetooth_toggle(self):
        # The exact live-log failure: "On koro blootooth" (misspelled, verb-first).
        for text in ("On koro blootooth", "bluetooth on koro", "ব্লুটুথ অন করো",
                     "bluetooth chalu koro", "bt on"):
            func, kwargs, _, msg = _parse_direct_os_action(text)
            self.assertEqual(func, "pc", text)
            self.assertEqual(kwargs, {"action": "bt_toggle", "state": "on"}, text)
        func, kwargs, _, _ = _parse_direct_os_action("bluetooth bondho koro")
        self.assertEqual(kwargs, {"action": "bt_toggle", "state": "off"})

    def test_wifi_toggle(self):
        func, kwargs, _, _ = _parse_direct_os_action("wifi on koro")
        self.assertEqual((func, kwargs), ("pc", {"action": "wifi_toggle", "state": "on"}))
        func, kwargs, _, _ = _parse_direct_os_action("wi-fi off koro")
        self.assertEqual(kwargs, {"action": "wifi_toggle", "state": "off"})

    def test_lock(self):
        func, kwargs, _, _ = _parse_direct_os_action("lock koro")
        self.assertEqual((func, kwargs), ("perform_shortcut", {"action": "lock"}))
        # "unlock" must NOT match the lock action (word-boundary check: no
        # boundary between 'n' and 'l' inside "unlock").
        result = _parse_direct_os_action("unlock the door")
        self.assertNotEqual(result, ("perform_shortcut", {"action": "lock"}, None, "PC lock kore dilam."))

    def test_camera_photo(self):
        for text in ("Take photo", "click a picture", "selfie tule dao"):
            with self.subTest(text=text):
                func, kwargs, control, display_msg = _parse_direct_os_action(text)
                self.assertEqual((func, kwargs), ("pc", {"action": "camera_photo"}))
                self.assertIsNone(control)
                self.assertIsNone(display_msg)

    def test_battery_status(self):
        func, kwargs, _, display_msg = _parse_direct_os_action("battery koto ache")
        self.assertEqual((func, kwargs), ("pc", {"action": "battery"}))
        self.assertIsNone(display_msg)  # raw tool result is shown, not a canned message
        func_result = _format_direct_os_response("pc", "Battery: 80% Charging\nPlan: Balanced", display_msg)
        self.assertIn("Battery: 80%", func_result)

    def test_power_actions_use_unified_pc_router(self):
        cases = {
            "Shutdown koro": "shutdown",
            "PC shutdown koro": "shutdown",
            "restart koro": "restart",
            "laptop sleep koro": "sleep",
            "hibernate koro": "hibernate",
            "কম্পিউটার বন্ধ করো": "shutdown",
        }
        for text, action in cases.items():
            with self.subTest(text=text):
                func, kwargs, _, _ = _parse_direct_os_action(text)
                self.assertEqual((func, kwargs), ("pc", {"action": action}))

    def test_app_or_media_close_is_not_power_action(self):
        for text in ("Chrome বন্ধ করো", "গান বন্ধ করো", "notepad close koro"):
            with self.subTest(text=text):
                result = _parse_direct_os_action(text)
                self.assertFalse(
                    result and result[0] == "pc" and result[1].get("action") == "shutdown"
                )

    def test_bt_wifi_questions_go_to_llm(self):
        # State questions must NOT toggle — they fall through to the LLM path.
        self.assertIsNone(_parse_direct_os_action("bluetooth ki on ache?"))
        self.assertIsNone(_parse_direct_os_action("bluetooth on ache"))
        self.assertIsNone(_parse_direct_os_action("wifi status dekhao"))
        # Bare mention with no on/off intent → LLM.
        self.assertIsNone(_parse_direct_os_action("bluetooth"))

    def test_blockers_and_complex_return_none(self):
        self.assertIsNone(_parse_direct_os_action("volume keno kaj korche na"))   # complaint
        self.assertIsNone(_parse_direct_os_action("baba ke volume pathao"))       # 'send' blocker
        self.assertIsNone(_parse_direct_os_action("notepad e likhe dao onek boro ekta message"))  # too long
        self.assertIsNone(_parse_direct_os_action("kemon acho"))                  # chit-chat
        self.assertIsNone(_parse_direct_os_action("volume barao"))                # no target level → LLM


class TestExtractLevel(unittest.TestCase):
    def test_valid_and_out_of_range(self):
        self.assertEqual(_extract_os_level("volume 40 koro"), 40)
        self.assertEqual(_extract_os_level("set 0"), 0)
        self.assertEqual(_extract_os_level("brightness 100"), 100)
        self.assertIsNone(_extract_os_level("volume 150"))   # >100
        self.assertIsNone(_extract_os_level("volume barao"))  # no number


class TestFormatResponse(unittest.TestCase):
    def test_error_is_surfaced(self):
        out = _format_direct_os_response("change_volume", "ERROR: Failed to set volume", "Volume set kore dilam.")
        self.assertIn("korte parlam na", out)

    def test_err_prefix_is_surfaced(self):
        # Unified tools return "ERR:" (not "ERROR:") — must never read as success.
        out = _format_direct_os_response("pc", "ERR: No Bluetooth adapter found.", "Bluetooth on kore dilam.")
        self.assertIn("korte parlam na", out)

    def test_pc_success_uses_display_msg(self):
        out = _format_direct_os_response("pc", "OK: Bluetooth turned on.", "Bluetooth on kore dilam.")
        self.assertEqual(out, "Bluetooth on kore dilam.")

    def test_success_uses_display_msg(self):
        out = _format_direct_os_response("change_volume", "SUCCESS: Changed system volume to 50%.", "Volume 50% kore dilam.")
        self.assertEqual(out, "Volume 50% kore dilam.")

    def test_clipboard_shows_content_and_empty(self):
        self.assertIn("hello world", _format_direct_os_response("read_clipboard", "hello world", None))
        self.assertIn("khali", _format_direct_os_response("read_clipboard", "   ", None))

    def test_clipboard_truncates_long_content(self):
        out = _format_direct_os_response("read_clipboard", "x" * 2000, None)
        self.assertLess(len(out), 700)  # truncated to ~500 + prefix


if __name__ == "__main__":
    unittest.main()
