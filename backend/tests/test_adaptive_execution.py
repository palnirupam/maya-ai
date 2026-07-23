import unittest
from unittest.mock import AsyncMock, patch

from backend.brain.agents.execution_policy import (
    adaptive_tool_round_limit,
    build_execution_brief,
    requires_tool_completion,
)
from backend.brain.reasoning.analysis_pass import AnalysisResult


class TestExecutionPolicy(unittest.TestCase):
    def test_execution_brief_is_flexible_and_bounded(self):
        graph = {
            "tasks": [
                {
                    "id": f"step_{idx}",
                    "description": f"Do task {idx}",
                    "depends_on": [f"step_{idx - 1}"] if idx > 1 else [],
                }
                for idx in range(1, 13)
            ]
        }

        brief = build_execution_brief(graph, "finish the whole job", max_steps=4)

        self.assertIn("ADAPTIVE EXECUTION PLAN", brief)
        self.assertIn("flexible checklist", brief)
        self.assertIn("Re-plan when tool results change", brief)
        self.assertIn("plus 8 additional", brief)
        self.assertNotIn("Do task 5", brief)

    def test_simple_turn_limits_stay_unchanged(self):
        self.assertEqual(adaptive_tool_round_limit("OS_EXECUTOR", 2), 6)
        self.assertEqual(adaptive_tool_round_limit("RESEARCHER", 3), 3)

    def test_complex_work_gets_more_room_but_is_capped(self):
        graph = {"tasks": [{"id": str(i)} for i in range(20)]}
        self.assertEqual(adaptive_tool_round_limit("OS_EXECUTOR", 20, graph), 12)
        self.assertEqual(adaptive_tool_round_limit("CODER", 20, graph), 8)

    def test_real_actions_require_tool_completion(self):
        self.assertTrue(requires_tool_completion("OS_EXECUTOR", "volume 50 koro"))
        self.assertTrue(requires_tool_completion("RESEARCHER", "latest AI news khuje dao"))
        self.assertTrue(requires_tool_completion("CODER", "run the python file main.py"))
        self.assertTrue(requires_tool_completion("CHAT", "ekta habit tracker banao"))
        self.assertFalse(requires_tool_completion("CODER", "show me a Python example"))
        self.assertFalse(requires_tool_completion("CHAT", "kemon acho"))


class TestAdaptivePlanIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_complex_plan_continues_through_full_agent_loop(self):
        from backend.brain.agents import agent_team

        graph = {
            "tasks": [
                {
                    "id": "step_1",
                    "type": "LLM_REASONING",
                    "description": "Understand the request",
                    "depends_on": [],
                },
                {
                    "id": "step_2",
                    "type": "LLM_REASONING",
                    "description": "Produce the final result",
                    "depends_on": ["step_1"],
                },
            ]
        }
        analysis = AnalysisResult(
            complexity_score=9,
            model_tier="thinking",
            fast_path_eligible=False,
            needs_task_graph=True,
            task_graph=graph,
        )
        captured_contexts = []

        async def fake_stream(context, *args, **kwargs):
            captured_contexts.append(context)
            yield "kaj complete"

        with (
            patch("backend.brain.reasoning.analysis_pass.run_heuristic_pass", return_value=analysis),
            patch(
                "backend.brain.reasoning.analysis_pass.build_task_graph_if_needed",
                new=AsyncMock(return_value=analysis),
            ),
            patch.object(agent_team, "_fast_route", return_value=["CHAT"]),
            patch.object(agent_team, "get_maya_tools", return_value=[]),
            patch("backend.skills.skill_watcher.get_dynamic_tools", return_value=[]),
            patch.object(agent_team.gemini_adapter, "generate_stream", side_effect=fake_stream),
        ):
            chunks = []
            async for chunk in agent_team.execute_workflow(
                "adaptive-plan-test",
                "Handle this complicated request carefully",
                [],
            ):
                chunks.append(chunk)

        text = "".join(chunk for chunk in chunks if isinstance(chunk, str))
        self.assertIn("kaj complete", text)
        self.assertTrue(captured_contexts)
        self.assertTrue(
            any(
                "ADAPTIVE EXECUTION PLAN" in message.get("content", "")
                for message in captured_contexts[0]
            )
        )
        self.assertTrue(
            any(
                isinstance(chunk, dict)
                and chunk.get("data", {}).get("active_agent") == "Planner"
                for chunk in chunks
            )
        )


if __name__ == "__main__":
    unittest.main()
