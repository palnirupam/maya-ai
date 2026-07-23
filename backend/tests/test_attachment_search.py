"""Regression tests for fuzzy attachment file search (_find_file_in_search_dirs).

Bug: the searcher matched a file only when the WHOLE query was a contiguous
substring of the filename (`if query_lower in fname.lower()`). So a natural
spoken request like "Aridam dada hostel issue pdf ta" never matched a file
actually named "Hostel Issue Aridam.pdf" — the tool returned "not found", and
the agent gave up with meta-commentary instead of sending.

Fix: token-based, order-independent fuzzy matching (_parse_file_query +
_file_match_tier). These tests lock in that loose multi-word descriptions match,
extension hints are honored, and unrelated files are rejected.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest

from backend.tools.desktop.advanced.system_tools import (
    _parse_file_query,
    _file_match_tier,
)


class TestParseFileQuery(unittest.TestCase):
    def test_loose_multiword_with_trailing_filler_and_ext_word(self):
        tokens, ext = _parse_file_query("Aridam dada hostel issue pdf ta")
        self.assertEqual(ext, ".pdf")            # bare "pdf" → ext hint
        self.assertNotIn("pdf", tokens)          # ext word not a name token
        self.assertNotIn("ta", tokens)           # filler stripped
        self.assertIn("hostel", tokens)
        self.assertIn("issue", tokens)
        self.assertIn("aridam", tokens)

    def test_real_suffix_extension(self):
        tokens, ext = _parse_file_query("report.pdf")
        self.assertEqual(ext, ".pdf")
        self.assertEqual(tokens, ["report"])

    def test_no_extension(self):
        tokens, ext = _parse_file_query("resume")
        self.assertEqual(ext, "")
        self.assertEqual(tokens, ["resume"])

    def test_ext_word_midphrase(self):
        tokens, ext = _parse_file_query("syllabus rrb pdf")
        self.assertEqual(ext, ".pdf")
        self.assertIn("syllabus", tokens)
        self.assertIn("rrb", tokens)

    def test_dotted_phrase_does_not_poison_extension(self):
        # Audit regression: splitext on the whole phrase yielded ext=".1 pdf"
        # which matched no file. Must resolve to the real extension instead.
        tokens, ext = _parse_file_query("project 2.1 pdf")
        self.assertEqual(ext, ".pdf")
        self.assertIn("project", tokens)

    def test_version_in_name_keeps_real_suffix(self):
        tokens, ext = _parse_file_query("report v2.final.docx")
        self.assertEqual(ext, ".docx")
        self.assertIn("report", tokens)


class TestFileMatchTier(unittest.TestCase):
    def setUp(self):
        self.tokens, self.ext = _parse_file_query("Aridam dada hostel issue pdf ta")

    def test_partial_match_found_when_some_tokens_present(self):
        # Real file lacks "dada" but has 3/4 tokens → partial (tier 1), FOUND.
        tier, hits = _file_match_tier("Hostel Issue Aridam.pdf", self.tokens, self.ext)
        self.assertGreaterEqual(tier, 1)
        self.assertEqual(hits, 3)

    def test_half_tokens_is_enough(self):
        tier, hits = _file_match_tier("Hostel Issue.pdf", self.tokens, self.ext)
        self.assertGreaterEqual(tier, 1)   # 2/4 tokens == threshold
        self.assertEqual(hits, 2)

    def test_all_tokens_is_strong_tier(self):
        tier, hits = _file_match_tier("Aridam Dada - Hostel Issue.pdf", self.tokens, self.ext)
        self.assertEqual(tier, 2)
        self.assertEqual(hits, 4)

    def test_extension_hint_rejects_wrong_type(self):
        # Same name but a .docx while user said "pdf" → rejected.
        tier, _ = _file_match_tier("Hostel Issue Aridam.docx", self.tokens, self.ext)
        self.assertEqual(tier, 0)

    def test_unrelated_file_rejected(self):
        tier, _ = _file_match_tier("quarterly_invoice.pdf", self.tokens, self.ext)
        self.assertEqual(tier, 0)   # zero token overlap

    def test_single_token_exact(self):
        tokens, ext = _parse_file_query("resume")
        tier, hits = _file_match_tier("My_Resume_2024.pdf", tokens, ext)
        self.assertEqual(tier, 2)
        self.assertEqual(hits, 1)

    def test_ranking_prefers_more_hits(self):
        # Simulate the searcher's key: (tier, ext_pref, hits). More hits wins.
        a = _file_match_tier("Hostel Issue.pdf", self.tokens, self.ext)          # (1, 2)
        b = _file_match_tier("Aridam Hostel Issue.pdf", self.tokens, self.ext)   # (1, 3)
        self.assertGreater(b[1], a[1])


if __name__ == "__main__":
    unittest.main()
