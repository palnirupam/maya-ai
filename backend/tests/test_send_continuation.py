"""Unit tests for send-flow continuation routing (the "Pintu bug").

Transcript that motivated this:
    User: "Pintu ke hi send kor"        -> OS_EXECUTOR, get_contact_number fails,
                                           Maya asks for the number / message text
    User: "Likho je valo achis"         -> misrouted to CHAT (no routable keywords),
                                           whose only tools are canvas + pc_optimizer
                                           skills, so Maya announced she had no
                                           WhatsApp tool and the flow died.

Covers the pending-send stickiness in _fast_route and the generalized
context anchoring in _tool_router_query.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest

from backend.brain.agents.agent_team import (
    _fast_route,
    _tool_router_query,
    _carries_tool_signal,
)


class TestPendingSendRouting(unittest.TestCase):
    def test_message_content_reply_sticks_to_os_executor(self):
        # The exact Pintu-bug turn: supplies the message text, zero keywords.
        self.assertEqual(
            _fast_route("Likho je valo achis", "OS_EXECUTOR", pending_send=True),
            ["OS_EXECUTOR"],
        )

    def test_bare_phone_number_reply_sticks_to_os_executor(self):
        # The inevitable next turn: Maya asked for Pintu's number.
        self.assertEqual(
            _fast_route("9876543210", "OS_EXECUTOR", pending_send=True),
            ["OS_EXECUTOR"],
        )

    def test_pick_from_list_reply_sticks_to_os_executor(self):
        # CLARIFICATION_NEEDED answers ("prothom ta") have no keywords either.
        self.assertEqual(
            _fast_route("prothom ta", "OS_EXECUTOR", pending_send=True),
            ["OS_EXECUTOR"],
        )

    def test_explicit_new_intent_beats_pending_send(self):
        # The user abandoned the send flow for a research question — the
        # explicit pattern must win over the flag.
        self.assertEqual(
            _fast_route("aajker khobor ki", "OS_EXECUTOR", pending_send=True),
            ["RESEARCHER"],
        )

    def test_without_flag_number_reply_short_circuits_to_chat(self):
        # Documents the pre-existing baseline the flag exists to override:
        # short non-question fragments collapse to CHAT.
        self.assertEqual(_fast_route("9876543210", "OS_EXECUTOR"), ["CHAT"])


class TestToolRouterQueryAnchoring(unittest.TestCase):
    HISTORY = [
        {"role": "user", "content": "Pintu ke hi send kor"},
        {"role": "assistant", "content": "Pintu nam e contact nei — number ta bolo."},
    ]

    def test_bare_number_reply_anchors_to_send_turn(self):
        # Without the anchor the ranking query is just digits, which starves
        # the delivery tools; anchored, the send-intent net fires.
        q = _tool_router_query("9876543210", self.HISTORY)
        self.assertEqual(q, "Pintu ke hi send kor 9876543210")

    def test_signal_bearing_message_is_not_anchored(self):
        q = _tool_router_query("whatsapp e Pintu ke message pathao", self.HISTORY)
        self.assertEqual(q, "whatsapp e Pintu ke message pathao")

    def test_no_history_returns_bare_text(self):
        self.assertEqual(_tool_router_query("9876543210", []), "9876543210")

    def test_walkback_past_signalless_turns(self):
        # Chain of bare adjustments still finds the anchoring keyword
        # (pre-existing behavior of the modifier-only anchoring, kept intact).
        history = [
            {"role": "user", "content": "volume 20% koro"},
            {"role": "user", "content": "50 koro"},
        ]
        self.assertEqual(
            _tool_router_query("70 koro", history), "volume 20% koro 70 koro"
        )

    def test_write_verb_reply_carries_its_own_signal(self):
        # "Likho je valo achis" matches the extended send-intent regex, so the
        # delivery net fires even with no usable history to anchor to.
        self.assertTrue(_carries_tool_signal("Likho je valo achis"))

    def test_os_keyword_message_carries_signal(self):
        self.assertTrue(_carries_tool_signal("notepad kholo"))


if __name__ == "__main__":
    unittest.main()
