"""Regression tests for ThinkStripper.clean_full — the final-message cleanup
applied before any channel (Telegram/WhatsApp/WebSocket) shows text to the
user. Covers the live leak where Gemini echoed its own anti-hallucination
instruction verbatim, glued onto the real Bengali answer with no separator.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest

from backend.brain.providers.gemini_adapter import ThinkStripper


class TestCleanFullTagStripping(unittest.TestCase):
    def test_think_tags_removed(self):
        out = ThinkStripper.clean_full("<think>plan plan plan</think>Ready now.")
        self.assertEqual(out, "Ready now.")

    def test_no_leak_marker_returns_unchanged(self):
        out = ThinkStripper.clean_full("ব্লুটুথ অন করা হয়েছে।")
        self.assertEqual(out, "ব্লুটুথ অন করা হয়েছে।")


class TestCleanFullInstructionLeak(unittest.TestCase):
    """Exact strings observed live in the user's Telegram log."""

    def test_bt_on_leak_stripped(self):
        leaked = (
            "Do not explain your steps, just provide the final answer in the "
            "user's language (Bengali/Banglish). Do not use any companion "
            "terms. Keep it concise and professional.ব্লুটুথ অন করা হয়েছে।"
        )
        self.assertEqual(ThinkStripper.clean_full(leaked), "ব্লুটুথ অন করা হয়েছে।")

    def test_bt_off_leak_stripped(self):
        leaked = (
            "If the execution is complete, provide your final response to "
            "the user. Do not explain your steps, just provide the final "
            "answer in the user's language (Bengali/Banglish). Do not use "
            "any companion terms. Keep it concise and professional."
            "ব্লুটুথ বন্ধ করা হয়েছে।"
        )
        self.assertEqual(ThinkStripper.clean_full(leaked), "ব্লুটুথ বন্ধ করা হয়েছে।")

    def test_plain_english_answer_with_leak_marker_fails_safe(self):
        # No non-Latin block to recover -> must not eat real content.
        leaked = "Let's formulate the final response. The task is complete."
        out = ThinkStripper.clean_full(leaked)
        self.assertTrue(out)  # never empty


if __name__ == "__main__":
    unittest.main()
