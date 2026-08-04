"""Unit tests for the zero-LLM fast keyword router (`_fast_route` / `_OS_PATTERNS`).

Covers the system-control keywords added during the pc-tool feature audit
(lock/shutdown/restart/sleep/hibernate/battery/stats) — these previously fell
through to the Gemini router, which has a STRICT RULE to classify questions as
CHAT, risking the same misroute that caused the original bluetooth bug.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest

from backend.brain.agents.agent_team import _fast_route, _CANVAS_PATTERNS


class TestFastRouteSystemControl(unittest.TestCase):
    def test_camera_photo_routes_to_os_not_canvas(self):
        self.assertEqual(_fast_route("Take photo"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("click a picture"), ["OS_EXECUTOR"])

    def test_lock_routes_to_os_executor(self):
        self.assertEqual(_fast_route("PC lock koro"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("লক করো"), ["OS_EXECUTOR"])

    def test_shutdown_restart_routes_to_os_executor(self):
        self.assertEqual(_fast_route("shutdown koro"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("PC restart koro"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("reboot koro"), ["OS_EXECUTOR"])

    def test_sleep_hibernate_routes_to_os_executor(self):
        self.assertEqual(_fast_route("PC sleep e pathao"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("hibernate koro"), ["OS_EXECUTOR"])

    def test_battery_status_question_routes_to_os_executor(self):
        # The exact failure shape as the original bluetooth bug: a QUESTION
        # about real device state must not fall through to CHAT.
        self.assertEqual(_fast_route("battery koto ache?"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("ব্যাটারি koto percent ache"), ["OS_EXECUTOR"])

    def test_stats_routes_to_os_executor(self):
        self.assertEqual(_fast_route("cpu usage koto?"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("system stats dekhao"), ["OS_EXECUTOR"])

    def test_bare_ram_name_does_not_false_positive(self):
        # "Ram" is a common given name — bare "ram"/"cpu" alone must NOT match,
        # only the scoped "ram usage"/"cpu usage" combos should.
        self.assertIsNone(_fast_route("Ram ekhon kothay ache?"))

    def test_unlock_does_not_match_lock(self):
        # No word boundary between "un" and "lock" — must not misfire.
        self.assertIsNone(_fast_route("please unlock the gate for me"))


class TestResearchRoutingFixes(unittest.TestCase):
    """Audit findings: 'khobor' (very common Banglish for news) was missing from
    the research patterns, and 'what is my battery' matched both research and OS,
    wastefully collapsing to a research+OS pipeline for a pure status question."""

    def test_khobor_send_runs_research_then_os_pipeline(self):
        # "aajker khobor WhatsApp e pathao" — research (khobor) + deliver (os).
        self.assertEqual(
            _fast_route("aajker khobor whatsapp e pathao"),
            ["RESEARCHER", "OS_EXECUTOR"],
        )

    def test_khobor_alone_routes_to_researcher(self):
        self.assertEqual(_fast_route("aajker khobor ki"), ["RESEARCHER"])

    def test_what_is_battery_is_os_only_not_research_pipeline(self):
        # Device-status question: no web search hop.
        self.assertEqual(_fast_route("what is my battery percentage"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("what is the cpu usage right now"), ["OS_EXECUTOR"])

    def test_genuine_research_plus_os_still_pipelines(self):
        # A real web-lookup ("news") that is then delivered must keep both agents.
        self.assertEqual(
            _fast_route("latest news search kore whatsapp e pathao"),
            ["RESEARCHER", "OS_EXECUTOR"],
        )

    def test_today_new_ta_pdf_email_runs_background_pipeline(self):
        self.assertEqual(
            _fast_route(
                "Achha ajker West Bengal er new ta pdf create kore "
                "palnirupam7@gmail.com ei gmail e send kore dao"
            ),
            ["RESEARCHER", "OS_EXECUTOR"],
        )

    def test_unrelated_new_ta_file_is_not_research(self):
        self.assertEqual(
            _fast_route("new ta file delete koro"),
            ["OS_EXECUTOR"],
        )


class TestShortMessageRouting(unittest.TestCase):
    """Audit finding: the second <=3-word branch in _fast_route was unreachable,
    so short conversational fillers fell through to the paid Gemini router."""

    def test_short_non_question_filler_routes_to_chat(self):
        self.assertEqual(_fast_route("ok thanks"), ["CHAT"])
        self.assertEqual(_fast_route("accha thik ache"), ["CHAT"])

    def test_short_greeting_routes_to_chat(self):
        self.assertEqual(_fast_route("hi maya"), ["CHAT"])
        self.assertEqual(_fast_route("hello"), ["CHAT"])

    def test_short_question_does_not_force_chat(self):
        # A short question should still fall through so the LLM/Gemini router can
        # decide; previously the unreachable branch would have forced CHAT here.
        self.assertIsNone(_fast_route("ki?"))

    def test_bare_document_routes_to_file_capable_os_agent(self):
        self.assertEqual(_fast_route("Document"), ["OS_EXECUTOR"])
        self.assertEqual(_fast_route("Documents"), ["OS_EXECUTOR"])

    def test_file_list_selection_stays_with_os_agent(self):
        self.assertEqual(
            _fast_route("3 tai", last_agent="OS_EXECUTOR"),
            ["OS_EXECUTOR"],
        )
        self.assertEqual(
            _fast_route("all three", last_agent="OS_EXECUTOR"),
            ["OS_EXECUTOR"],
        )


class TestCanvasPatternFalsePositive(unittest.TestCase):
    """Live bug: 'bana.*de' (unbounded, no word boundary on "de") greedily
    matched "banao ... de[sktop]" across unrelated words, misrouting a
    research+save request to CHAT (which has no file-write tool) — Maya then
    hallucinated "I can't save files directly." Fixed with \\bbana.{0,20}\\bde\\b."""

    def test_research_and_save_request_not_treated_as_canvas(self):
        t = "news search koro then summary banao then desktop e save koro"
        self.assertIsNone(_CANVAS_PATTERNS.search(t.lower()))
        self.assertEqual(_fast_route(t), ["RESEARCHER", "OS_EXECUTOR"])

    def test_other_de_prefixed_words_dont_false_positive(self):
        for t in ("file ta delete koro", "khobor dekhao", "decide korte hobe ki korbo"):
            self.assertIsNone(_CANVAS_PATTERNS.search(t.lower()), t)

    def test_genuine_bana_de_canvas_request_still_matches(self):
        for t in ("ekta habit tracker bana de", "amake ekta widget bana de please", "kisu ekta bana de"):
            self.assertTrue(_CANVAS_PATTERNS.search(t.lower()), t)


if __name__ == "__main__":
    unittest.main()
