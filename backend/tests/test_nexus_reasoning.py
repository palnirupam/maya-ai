"""Regression tests for bugs found in the "NEXUS" reasoning-layer audit
(TaskGraph failure modes, IntentSentinel dead-end approval, BudgetManager
downgrade wiring). See conversation history for the bug-hunt writeup.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import asyncio
import unittest

from backend.brain.reasoning.workflow_engine import (
    GraphExecutionState,
    execute_task_graph,
    STEP_DONE,
    STEP_FAILED,
    STEP_SKIPPED,
    STEP_CANCELLED,
    STEP_AWAITING_USER,
)
from backend.brain.agents.intent_sentinel import IntentSentinel
from backend.brain.budget_manager import BudgetManager


class TestFailureModeDistinctness(unittest.TestCase):
    """Bug: ASK_USER previously set status=STEP_FAILED (identical to a plain
    failure) and the `actions` list documenting "awaiting_user" was computed
    but never read anywhere — so it never actually paused anything, and the
    graph runner silently kept executing unrelated downstream steps past an
    unresolved user question. Fixed by giving it its own STEP_AWAITING_USER
    status that halts the whole graph."""

    def _graph(self, failure_mode):
        return [
            {"id": "step_1", "description": "d1", "depends_on": [], "failure_mode": failure_mode},
            {"id": "step_2", "description": "d2", "depends_on": ["step_1"], "failure_mode": "RETRY"},
        ]

    def test_ask_user_produces_distinct_status(self):
        state = GraphExecutionState(self._graph("ASK_USER"))
        state.handle_failure("step_1", "ASK_USER")
        self.assertEqual(state.get_status("step_1"), STEP_AWAITING_USER)
        self.assertNotEqual(STEP_AWAITING_USER, STEP_FAILED)

    def test_skip_optional_only_skips_itself(self):
        state = GraphExecutionState(self._graph("SKIP_OPTIONAL"))
        state.handle_failure("step_1", "SKIP_OPTIONAL")
        self.assertEqual(state.get_status("step_1"), STEP_SKIPPED)
        self.assertEqual(state.get_status("step_2"), "pending")  # untouched

    def test_cancel_subtree_cascades_downstream(self):
        state = GraphExecutionState(self._graph("CANCEL_SUBTREE"))
        state.handle_failure("step_1", "CANCEL_SUBTREE")
        self.assertEqual(state.get_status("step_1"), STEP_FAILED)
        self.assertEqual(state.get_status("step_2"), STEP_CANCELLED)

    def test_awaiting_user_dependent_is_blocked(self):
        state = GraphExecutionState(self._graph("ASK_USER"))
        state.handle_failure("step_1", "ASK_USER")
        self.assertTrue(state.has_cancelled_dep({"depends_on": ["step_1"]}))
        self.assertFalse(state.all_deps_satisfied({"depends_on": ["step_1"]}))


class TestWorkflowHaltsOnAskUser(unittest.TestCase):
    """Live bug: a graph with an independent (no-dependency) step after an
    ask_user step used to keep executing that independent step, silently
    proceeding past a decision the graph said it needed the user for."""

    def test_independent_step_does_not_run_after_ask_user(self):
        graph = {
            "tasks": [
                {"id": "step_1", "type": "TOOL_CALL", "tool_name": "nonexistent_tool",
                 "description": "will fail", "depends_on": [], "failure_mode": "ASK_USER"},
                {"id": "step_2", "type": "LLM_REASONING", "description": "independent",
                 "depends_on": [], "failure_mode": "RETRY"},
            ]
        }

        async def run():
            chunks = []
            async for c in execute_task_graph(graph, "sid", [], all_tools=[]):
                chunks.append(c)
            return chunks

        chunks = asyncio.run(run())
        text_chunks = "".join(c for c in chunks if isinstance(c, str))
        self.assertIn("awaiting your response", text_chunks)
        # step_2 must NOT have executed — its LLM step would raise (no adapter
        # configured in this test) or otherwise produce step-2 output; the
        # graph must have returned right after step_1 instead.
        self.assertNotIn("Step 2", text_chunks)


class TestIntentSentinelNoDeadEnd(unittest.TestCase):
    """Bug: IntentSentinel.evaluate() could return status="needs_approval" for
    shutdown/restart/reboot/poweroff text, but nothing in agent_team.py could
    actually pause and resume on that verdict — it just asked "Yes/No?" and
    ended the turn, so a "yes" reply started a fresh turn with no memory of
    the pending shutdown and nothing ever executed. Fixed by removing the
    dead-end and letting the real DANGER_TOOLS approval gate (which does a
    real tool_call_request round trip) handle these actions instead."""

    def test_poweroff_no_longer_returns_needs_approval(self):
        decision = IntentSentinel.evaluate(
            "PC poweroff koro", "professional",
            ["terminal.execute", "filesystem.write"]
        )
        self.assertNotEqual(decision.status, "needs_approval")

    def test_shutdown_text_allowed_through_to_real_gate(self):
        decision = IntentSentinel.evaluate(
            "shutdown koro", "professional",
            ["terminal.execute", "filesystem.write"]
        )
        self.assertEqual(decision.status, "allow")

    def test_genuinely_destructive_commands_still_blocked(self):
        decision = IntentSentinel.evaluate(
            "format C: drive", "professional",
            ["terminal.execute", "filesystem.write"]
        )
        self.assertEqual(decision.status, "block")


class TestBudgetManagerActuallyTracksUsage(unittest.TestCase):
    """Bug: BudgetManager.record_usage() — the ONLY method that increments
    tokens_used and can trigger a downgrade — was never called anywhere in
    the codebase. set_requested_tier()/pop_downgrade_notification() were
    wired up, but with tokens_used permanently stuck at 0 a downgrade could
    never actually happen. Fixed by calling record_usage() from
    orchestrator.py after every turn."""

    def test_record_usage_accumulates_and_downgrades(self):
        bm = BudgetManager()
        sid = "test-session"
        bm.set_requested_tier(sid, "thinking")
        self.assertEqual(bm.get_active_tier(sid), "thinking")

        # Under budget — no downgrade yet.
        result = bm.record_usage(sid, 1000, 1000)
        self.assertIsNone(result)
        self.assertEqual(bm.get_active_tier(sid), "thinking")

        # Push past the "thinking" tier's 80_000 token budget.
        result = bm.record_usage(sid, 50_000, 40_000)
        self.assertEqual(result, ("thinking", "reasoning"))
        self.assertEqual(bm.get_active_tier(sid), "reasoning")

        msg = bm.pop_downgrade_notification(sid)
        self.assertIsNotNone(msg)
        self.assertIsNone(bm.pop_downgrade_notification(sid))  # only notified once


if __name__ == "__main__":
    unittest.main()
