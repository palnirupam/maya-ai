"""Regression tests for crypto subsystem fixes."""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest
from unittest.mock import patch

from backend.database.crypto import (
    CryptoManager,
    _get_hardware_fingerprint,
    _candidate_fingerprints,
    _build_ciphers,
)


class TestHardwareFingerprintDrift(unittest.TestCase):
    """Audit B2: during a WMI/PowerShell outage the primary fingerprint must
    NOT become the unstable '_' string; it must stay the stable fallback so
    data written during the outage remains decryptable after recovery.
    """

    def test_outage_fingerprint_is_stable_fallback(self):
        with patch("backend.database.crypto._hardware_components", return_value=("", "")):
            fp = _get_hardware_fingerprint()
            candidates = _candidate_fingerprints()
            multi, primary = _build_ciphers()

            self.assertEqual(fp, "fallback_static_fingerprint_for_safety")
            # Encryption primary must be the stable fallback, not the transient '_'.
            self.assertEqual(candidates[0], "_")
            self.assertIn(fp, candidates)

    def test_partial_outage_uses_fallback_not_board_or_cpu_only(self):
        with patch("backend.database.crypto._hardware_components", return_value=("BOARD42", "")):
            fp = _get_hardware_fingerprint()
            self.assertEqual(fp, "fallback_static_fingerprint_for_safety")
            self.assertNotEqual(fp, "BOARD42_")

    def test_legacy_underscore_key_still_recoverable(self):
        """Data written under the old '_' primary key must still decrypt."""
        with patch("backend.database.crypto._hardware_components", return_value=("", "")):
            with patch("backend.database.crypto._get_hardware_fingerprint", return_value="_"):
                multi, primary = _build_ciphers()
            token = primary.encrypt("legacy secret".encode()).decode()

        with patch("backend.database.crypto._hardware_components", return_value=("BOARD", "CPU")):
            multi2, _ = _build_ciphers()
            decrypted = multi2.decrypt(token.encode()).decode()
            self.assertEqual(decrypted, "legacy secret")


if __name__ == "__main__":
    unittest.main()
