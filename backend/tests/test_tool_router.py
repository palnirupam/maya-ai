"""Unit tests for the dynamic tool router (backend/brain/agents/tool_router.py).

The embedder is mocked with a deterministic bag-of-words model so semantic
ranking is predictable and no network is touched. Disk cache is stubbed out so
tests are hermetic.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import re
import unittest
from unittest.mock import patch

from backend.brain.agents import tool_router


# ── Fake tools — the router fingerprints name + first docstring line ─────────
def send_background_email():
    """Send an email in the background via Gmail."""
def read_background_email():
    """Read and fetch recent emails from the Gmail inbox."""
def trash_background_email():
    """Move an email to trash or delete an email."""
def click_mouse():
    """Perform a left mouse click at the cursor."""
def move_mouse_to():
    """Move the mouse cursor to screen coordinates."""
def control_brightness():
    """Increase or decrease the screen brightness."""
def whatsapp_send_message():
    """Send a WhatsApp message to a phone contact."""
def take_verified_screenshot():
    """Capture a screenshot to verify an action."""
def change_interaction_mode():
    """Switch assistant mode coding professional friendly."""
def manage_system_state():
    """Shutdown or sleep the assistant system."""

ALL_TOOLS = [
    send_background_email, read_background_email, trash_background_email,
    click_mouse, move_mouse_to, control_brightness, whatsapp_send_message,
    take_verified_screenshot, change_interaction_mode, manage_system_state,
]

_VOCAB = ["email", "gmail", "mail", "send", "read", "fetch", "trash", "delete",
          "inbox", "mouse", "click", "cursor", "move", "coordinates",
          "brightness", "screen", "volume", "audio", "whatsapp", "message",
          "phone", "contact", "screenshot", "verify", "action", "mode",
          "shutdown", "sleep", "system",
          # file-op vocab (for the `file` safety-net test)
          "file", "save", "desktop", "txt", "document", "note", "report", "pdf",
          # memory vocab (for MCP memory tool tests)
          "memory", "nodes", "graph", "remember", "birthday", "tell", "yesterday", "summarize",
          # app / system vocab
          "chrome", "open",
          # romanized-Bengali token no tool signature contains — yields a valid
          # query vector that is ~0-similar to EVERY tool (rank-floor test)
          "valo"]


def _bow(text):
    """Deterministic bag-of-words 'embedding' over a small fixed vocabulary."""
    toks = re.findall(r"[a-z]+", (text or "").lower())
    return [float(toks.count(w)) for w in _VOCAB]


def _names(tools):
    return {tool_router._get_tool_name(t) for t in tools if tool_router._get_tool_name(t)}


class TestToolRouter(unittest.TestCase):
    def setUp(self):
        # Isolate from disk + any prior in-memory state.
        tool_router._vec_cache.clear()
        self._p_load = patch.object(tool_router, "_load_disk_cache", lambda: None)
        self._p_save = patch.object(tool_router, "_save_disk_cache", lambda: None)
        self._p_load.start()
        self._p_save.start()

    def tearDown(self):
        self._p_load.stop()
        self._p_save.stop()

    def test_semantic_picks_relevant_drops_irrelevant(self):
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "gmail e mail pathao send email", ALL_TOOLS))
        self.assertIn("send_background_email", result)
        self.assertIn("read_background_email", result)
        self.assertNotIn("click_mouse", result)
        self.assertNotIn("control_brightness", result)

    def test_always_include_survives(self):
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "send email to baba", ALL_TOOLS))
        self.assertIn("take_verified_screenshot", result)
        self.assertIn("change_interaction_mode", result)
        self.assertIn("manage_system_state", result)

    def test_embedding_down_keyword_fallback(self):
        # Embedder unavailable -> keyword path; 'email' hits exactly 3 tools.
        with patch.object(tool_router, "_get_embedding", side_effect=lambda t: None):
            result = _names(tool_router.select_relevant_tools("email", ALL_TOOLS))
        self.assertIn("send_background_email", result)
        self.assertIn("read_background_email", result)
        self.assertIn("trash_background_email", result)
        self.assertNotIn("click_mouse", result)  # proves it isn't "all candidates"

    def test_weak_keyword_falls_back_to_all(self):
        # 'brightness' matches only 1 tool (< _KW_MIN_HITS) -> pass through ALL.
        with patch.object(tool_router, "_get_embedding", side_effect=lambda t: None):
            result = tool_router.select_relevant_tools("brightness", ALL_TOOLS)
        self.assertEqual(_names(result), _names(ALL_TOOLS))

    def test_cache_avoids_re_embedding_tools(self):
        calls = {"n": 0}

        def counting(text):
            calls["n"] += 1
            return _bow(text)

        with patch.object(tool_router, "_get_embedding", side_effect=counting):
            tool_router.select_relevant_tools("send email", ALL_TOOLS)
            first = calls["n"]
            tool_router.select_relevant_tools("send email", ALL_TOOLS)
            second = calls["n"] - first
        # First call embeds every tool + the query; second embeds only the query.
        self.assertEqual(len(ALL_TOOLS) + 1, first)
        self.assertEqual(1, second)

    def test_never_raises_returns_all_on_error(self):
        with patch.object(tool_router, "_get_embedding", side_effect=RuntimeError("boom")):
            result = tool_router.select_relevant_tools("anything", ALL_TOOLS)
        self.assertEqual(_names(result), _names(ALL_TOOLS))

    def test_empty_candidates(self):
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            self.assertEqual(tool_router.select_relevant_tools("x", []), [])

    def test_send_intent_regex_covers_bengali_write_and_send_verbs(self):
        # "Likho je valo achis" (the Pintu bug) is the message-content turn of a
        # send flow — write/tell verbs must count as send intent, conjugations
        # included, or the delivery net never fires mid-flow.
        for phrase in (
            "Likho je valo achis",
            "lekho je kal asbo",
            "hi pathao",
            "bhejo ekhuni",
            "ke pathiyecho",
            "ওকে মেসেজ পাঠাও",
            "লিখে দাও ভালো আছি",
        ):
            self.assertIsNotNone(tool_router._SEND_INTENT_RE.search(phrase), phrase)

    def test_volume_turns_do_not_trip_send_net(self):
        # The net is query-gated to avoid bloating unrelated OS turns.
        for phrase in ("volume 20% koro", "brightness barao", "50 koro", "pc lock koro"):
            self.assertIsNone(tool_router._SEND_INTENT_RE.search(phrase), phrase)

    def test_bengali_write_reply_keeps_delivery_tools(self):
        # The Pintu bug end-to-end at the ranking layer: cross-lingual message
        # content ranks ~0 against every English tool signature, so selection
        # falls to the arbitrary rank-floor, which starved get_contact_number —
        # Maya then announced she had no WhatsApp tool. The likho/lekho verbs
        # in _SEND_INTENT_RE must fire the delivery net and rescue the flow.
        def get_contact_number():
            """Look up the saved number for a contact name."""

        tools = ALL_TOOLS + [get_contact_number]
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "Likho je valo achis", tools))
        self.assertIn("whatsapp_send_message", result)
        self.assertIn("get_contact_number", result)
        self.assertIn("send_background_email", result)
        self.assertNotIn("click_mouse", result)  # proves it isn't pass-through-all

    def test_pintu_first_send_turn_keeps_whatsapp_delivery_tools(self):
        def get_contact_number():
            """Look up the saved number for a contact name."""

        tools = ALL_TOOLS + [get_contact_number]
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "Pintu ke hi send koro", tools))
        self.assertIn("whatsapp_send_message", result)
        self.assertIn("get_contact_number", result)

    def test_file_tool_survives_ranking_for_save_query(self):
        # The `file` tool's terse signature ranks low against "save ... .txt", so
        # semantic ranking would drop it. The query-gated file safety net must
        # rescue it — otherwise OS_EXECUTOR can't write the file and only stalls.
        def file():
            """Universal operation router dispatcher."""  # deliberately no file-op words

        def note_saver():
            """Save a note to the desktop as a txt document."""

        def click_mouse2():
            """Perform a left mouse click at the cursor."""

        tools = [file, note_saver, click_mouse2, take_verified_screenshot]
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "save this to desktop as report.txt", tools))
        self.assertIn("file", result)          # rescued by the file safety net
        self.assertIn("note_saver", result)    # legitimately ranked in
        self.assertNotIn("click_mouse2", result)  # proves it isn't a pass-through-all

    def test_pdf_creation_tool_survives_email_report_ranking(self):
        def create_pdf():
            """Create a PDF report in the background."""

        tools = ALL_TOOLS + [create_pdf]
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "today news pdf create kore email e send koro", tools
            ))

        self.assertIn("create_pdf", result)
        self.assertIn("send_background_email", result)

    def test_background_media_tools_survive_cross_lingual_ranking(self):
        def play_youtube_background():
            """Headless stream dispatcher."""

        def stop_youtube_background():
            """Terminate the active headless stream."""

        tools = ALL_TOOLS + [play_youtube_background, stop_youtube_background]
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "amar favourite gaan ta chalao", tools
            ))

        self.assertIn("play_youtube_background", result)
        self.assertIn("stop_youtube_background", result)

    def test_mcp_dict_schemas_are_relevance_ranked(self):
        mcp_memory_schema = {
            "name": "memory__search_nodes",
            "description": "Search for nodes in the knowledge graph matching query",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        }
        mcp_read_graph = {
            "name": "memory__read_graph",
            "description": "Read the entire knowledge graph structure",
            "parameters": {"type": "object", "properties": {}},
        }
        tools = ALL_TOOLS + [mcp_memory_schema, mcp_read_graph]
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "CJP news baba ke whatsapp e send koro", tools
            ))

        self.assertIn("whatsapp_send_message", result)
        self.assertNotIn("memory__search_nodes", result)
        self.assertNotIn("memory__read_graph", result)

    def test_mcp_dict_schemas_retained_when_query_is_memory_related(self):
        mcp_memory_schema = {
            "name": "memory__search_nodes",
            "description": "Search for nodes in the knowledge graph matching query",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        }
        tools = ALL_TOOLS + [mcp_memory_schema]
        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            result = _names(tool_router.select_relevant_tools(
                "memory search nodes knowledge graph", tools
            ))

        self.assertIn("memory__search_nodes", result)

    def test_mcp_memory_tool_routing_6_regression_cases(self):
        mcp_tools = [
            {
                "name": "memory__create_entities",
                "description": "Create multiple new entities in the knowledge graph memory to remember facts",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "memory__search_nodes",
                "description": "Search for nodes and recall facts from yesterday in the knowledge graph matching query",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
            {
                "name": "memory__read_graph",
                "description": "Read and summarize the entire knowledge graph structure",
                "parameters": {"type": "object", "properties": {}},
            },
        ]
        all_candidates = ALL_TOOLS + mcp_tools

        with patch.object(tool_router, "_get_embedding", side_effect=_bow):
            # Case 1: "remember my birthday" -> memory tool MUST be present
            res1 = _names(tool_router.select_relevant_tools("remember my birthday", all_candidates))
            self.assertTrue(any(n.startswith("memory__") for n in res1), f"Case 1 failed: Expected memory tool for 'remember my birthday', got {res1}")

            # Case 2: "what did i tell you yesterday" -> memory tool MUST be present
            res2 = _names(tool_router.select_relevant_tools("what did i tell you yesterday", all_candidates))
            self.assertTrue(any(n.startswith("memory__") for n in res2), f"Case 2 failed: Expected memory tool for 'what did i tell you yesterday', got {res2}")

            # Case 3: "send whatsapp message" -> memory tool MUST NOT be present
            res3 = _names(tool_router.select_relevant_tools("send whatsapp message", all_candidates))
            self.assertFalse(any(n.startswith("memory__") for n in res3), f"Case 3 failed: Did not expect memory tool for 'send whatsapp message', got {res3}")

            # Case 4: "open chrome" -> memory tool MUST NOT be present
            def open_app():
                """Open a desktop application like chrome or notepad."""
            res4 = _names(tool_router.select_relevant_tools("open chrome", ALL_TOOLS + mcp_tools + [open_app]))
            self.assertFalse(any(n.startswith("memory__") for n in res4), f"Case 4 failed: Did not expect memory tool for 'open chrome', got {res4}")

            # Case 5: "search file report.pdf" -> memory tool MUST NOT be present
            res5 = _names(tool_router.select_relevant_tools("search file report.pdf", all_candidates))
            self.assertFalse(any(n.startswith("memory__") for n in res5), f"Case 5 failed: Did not expect memory tool for 'search file report.pdf', got {res5}")

            # Case 6: "summarize knowledge graph" -> memory tool MUST be present
            res6 = _names(tool_router.select_relevant_tools("summarize knowledge graph", all_candidates))
            self.assertTrue(any(n.startswith("memory__") for n in res6), f"Case 6 failed: Expected memory tool for 'summarize knowledge graph', got {res6}")


if __name__ == "__main__":
    unittest.main()
