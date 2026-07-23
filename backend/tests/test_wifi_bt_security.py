"""Security tests for the WiFi/Bluetooth tools: injection inputs must be
neutralized before reaching PowerShell / WLAN profile XML."""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import re
import unittest
from unittest.mock import patch

from backend.tools.desktop.advanced import bluetooth_tools
from backend.tools.desktop.advanced.wifi_tools import _build_wlan_xml, _sanitize_ssid


class TestBluetoothRemoveSanitization(unittest.TestCase):
    def test_injection_chars_stripped_before_powershell(self):
        captured = {}

        def fake_ps(cmd, timeout=10):
            captured["cmd"] = cmd
            return "not found"

        with patch.object(bluetooth_tools, "_ps", fake_ps):
            bluetooth_tools.bluetooth_remove_device("x'; Remove-Item C:\\ -Recurse #$(evil)")
        # Only the interpolated -match pattern matters (the rest of the script
        # is our own static PowerShell).
        pattern = re.search(r"-match '([^']*)'", captured["cmd"]).group(1)
        for bad in (";", "$", "(", ")", "#", "\\", "'", '"'):
            self.assertNotIn(bad, pattern)

    def test_empty_or_symbol_only_name_rejected_without_running(self):
        with patch.object(bluetooth_tools, "_ps") as ps:
            self.assertTrue(bluetooth_tools.bluetooth_remove_device("").startswith("ERR"))
            self.assertTrue(bluetooth_tools.bluetooth_remove_device("$();'").startswith("ERR"))
            ps.assert_not_called()


class TestWlanXmlEscaping(unittest.TestCase):
    def test_ssid_and_password_are_xml_escaped(self):
        xml = _build_wlan_xml("evil</name><x>", 'pw"&<>')
        self.assertNotIn("<x>", xml)
        self.assertIn("evil&lt;/name&gt;&lt;x&gt;", xml)
        # Quotes are harmless inside XML text nodes; structural chars must be escaped.
        self.assertIn('pw"&amp;&lt;&gt;', xml)

    def test_sanitize_ssid_strips_control_chars_and_length(self):
        self.assertEqual(_sanitize_ssid('My"Net\r\n'), "MyNet")
        self.assertEqual(len(_sanitize_ssid("x" * 100)), 32)
        self.assertEqual(_sanitize_ssid(None), "")


if __name__ == "__main__":
    unittest.main()
