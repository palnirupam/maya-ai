from unittest.mock import AsyncMock, patch

import pytest

from backend.brain.agents import agent_team
from backend.brain.reasoning.analysis_pass import AnalysisResult
from backend.tools.manifest import get_manifest
from backend.tools.verifier import ResultVerifier


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        "ERR: missing C:/Users/test/file.txt",
        "ERROR: Could not set volume.",
        "EXECUTION FAILED: process exited with code 1",
        "PYTHON EXECUTION FAILED: syntax error",
        "Tool 'file' raised an error: disk unavailable",
    ],
)
async def test_explicit_tool_failures_are_invalid_and_retryable(result: str) -> None:
    verified = await ResultVerifier.verify(
        "file", result, get_manifest("file")
    )

    assert not verified.valid
    assert verified.retryable
    assert verified.reason == result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        "ERR: protected path",
        "BLOCKED: Sensitive app on screen. Cannot capture screenshot.",
        "ERROR: PDF support is not installed.",
        "Tool 'file' is disabled or not available.",
        "ERROR: Permission denied by user.",
    ],
)
async def test_terminal_failures_are_invalid_but_not_retried(result: str) -> None:
    verified = await ResultVerifier.verify(
        "file", result, get_manifest("file")
    )

    assert not verified.valid
    assert not verified.retryable


@pytest.mark.asyncio
async def test_partial_file_result_is_invalid_and_not_retried() -> None:
    result = "PARTIAL: destination created, but source cleanup remains"

    verified = await ResultVerifier.verify("file", result, get_manifest("file"))

    assert not verified.valid
    assert not verified.retryable
    assert verified.reason == result


@pytest.mark.asyncio
async def test_success_and_embedded_error_text_remain_valid() -> None:
    manifest = get_manifest("file")

    assert (await ResultVerifier.verify("file", "OK: saved", manifest)).valid
    assert (
        await ResultVerifier.verify(
            "file",
            "Document contents:\nERROR: this is a quoted log line",
            manifest,
        )
    ).valid


def _analysis_result() -> AnalysisResult:
    return AnalysisResult(
        complexity_score=1,
        model_tier="fast",
        fast_path_eligible=True,
        needs_task_graph=False,
        task_graph=None,
    )


@pytest.mark.asyncio
async def test_agent_retries_retryable_failure_and_recovers() -> None:
    tool_results = iter(["ERR: missing C:/wrong.txt", "OK: C:/fixed.txt"])
    tool_calls = []

    async def file(**kwargs):
        tool_calls.append(kwargs)
        return next(tool_results)

    stream_round = 0

    async def fake_stream(*args, **kwargs):
        nonlocal stream_round
        stream_round += 1
        if stream_round == 1:
            yield {
                "type": "tool_call",
                "name": "file",
                "args": {"action": "read", "src": "C:/wrong.txt"},
            }
        else:
            yield "Recovered successfully."

    analysis = _analysis_result()
    with (
        patch("backend.brain.reasoning.analysis_pass.run_heuristic_pass", return_value=analysis),
        patch(
            "backend.brain.reasoning.analysis_pass.build_task_graph_if_needed",
            new=AsyncMock(return_value=analysis),
        ),
        patch.object(agent_team, "_fast_route", return_value=["OS_EXECUTOR"]),
        patch.object(agent_team, "_parse_direct_app_action", return_value=None),
        patch.object(agent_team, "_parse_direct_os_action", return_value=None),
        patch.object(agent_team, "get_maya_tools", return_value=[file]),
        patch("backend.skills.skill_watcher.get_dynamic_tools", return_value=[]),
        patch.object(agent_team.gemini_adapter, "generate_stream", side_effect=fake_stream),
        patch.object(
            agent_team.gemini_adapter,
            "generate_response",
            new=AsyncMock(
                return_value='```json\n{"action":"read","src":"C:/fixed.txt"}\n```'
            ),
        ) as replan,
    ):
        chunks = [
            chunk
            async for chunk in agent_team.execute_workflow(
                "verifier-retry-session",
                "Read the requested file",
                [],
            )
        ]

    assert len(tool_calls) == 2
    assert tool_calls[-1]["src"] == "C:/fixed.txt"
    replan.assert_awaited_once()
    assert "Recovered successfully." in "".join(
        chunk for chunk in chunks if isinstance(chunk, str)
    )


@pytest.mark.asyncio
async def test_agent_does_not_repeat_non_retryable_failure() -> None:
    tool_calls = []

    async def file(**kwargs):
        tool_calls.append(kwargs)
        return "ERR: protected path"

    stream_round = 0

    async def fake_stream(*args, **kwargs):
        nonlocal stream_round
        stream_round += 1
        if stream_round == 1:
            yield {
                "type": "tool_call",
                "name": "file",
                "args": {"action": "write", "src": "C:/maya-ai/x.txt", "dst": "x"},
            }
        else:
            yield "The requested path is protected."

    analysis = _analysis_result()
    replan = AsyncMock(return_value="{}")
    with (
        patch("backend.brain.reasoning.analysis_pass.run_heuristic_pass", return_value=analysis),
        patch(
            "backend.brain.reasoning.analysis_pass.build_task_graph_if_needed",
            new=AsyncMock(return_value=analysis),
        ),
        patch.object(agent_team, "_fast_route", return_value=["OS_EXECUTOR"]),
        patch.object(agent_team, "_parse_direct_app_action", return_value=None),
        patch.object(agent_team, "_parse_direct_os_action", return_value=None),
        patch.object(agent_team, "get_maya_tools", return_value=[file]),
        patch("backend.skills.skill_watcher.get_dynamic_tools", return_value=[]),
        patch.object(agent_team.gemini_adapter, "generate_stream", side_effect=fake_stream),
        patch.object(agent_team.gemini_adapter, "generate_response", new=replan),
    ):
        history = []
        chunks = [
            chunk
            async for chunk in agent_team.execute_workflow(
                "verifier-terminal-session",
                "Write this file to the protected project path",
                history,
            )
        ]

    assert len(tool_calls) == 1
    replan.assert_not_awaited()
    assert any(
        message.get("role") == "function"
        and message.get("content") == "ERR: protected path"
        for message in history
    )
    assert "The requested path is protected." in "".join(
        chunk for chunk in chunks if isinstance(chunk, str)
    )


@pytest.mark.asyncio
async def test_agent_never_auto_retries_executing_send_tool() -> None:
    tool_calls = []

    async def whatsapp_send_message(**kwargs):
        tool_calls.append(kwargs)
        return "ERROR: delivery result is unknown after timeout"

    stream_round = 0

    async def fake_stream(*args, **kwargs):
        nonlocal stream_round
        stream_round += 1
        if stream_round == 1:
            yield {
                "type": "tool_call",
                "name": "whatsapp_send_message",
                "args": {"contact_name": "919876543210", "message": "hello"},
            }
        else:
            yield "I could not verify whether the message was delivered."

    analysis = _analysis_result()
    replan = AsyncMock(return_value="{}")
    with (
        patch("backend.brain.reasoning.analysis_pass.run_heuristic_pass", return_value=analysis),
        patch(
            "backend.brain.reasoning.analysis_pass.build_task_graph_if_needed",
            new=AsyncMock(return_value=analysis),
        ),
        patch.object(agent_team, "_fast_route", return_value=["OS_EXECUTOR"]),
        patch.object(agent_team, "_parse_direct_app_action", return_value=None),
        patch.object(agent_team, "_parse_direct_os_action", return_value=None),
        patch.object(agent_team, "get_maya_tools", return_value=[whatsapp_send_message]),
        patch("backend.skills.skill_watcher.get_dynamic_tools", return_value=[]),
        patch.object(agent_team.gemini_adapter, "generate_stream", side_effect=fake_stream),
        patch.object(agent_team.gemini_adapter, "generate_response", new=replan),
    ):
        chunks = [
            chunk
            async for chunk in agent_team.execute_workflow(
                "send-no-retry-session",
                "Send hello on WhatsApp",
                [],
            )
        ]

    assert len(tool_calls) == 1
    replan.assert_not_awaited()
    assert "delivery was not completed" in "".join(
        chunk for chunk in chunks if isinstance(chunk, str)
    ).lower()


@pytest.mark.asyncio
async def test_approved_danger_tool_retries_only_with_the_approved_args() -> None:
    """BUG-022: an approval is bound to the exact tool + args the user saw.

    A retryable failure on an approved danger tool must never re-execute with
    LLM-replanned args (or a fallback tool) — that would run an operation the
    user never approved. Identical-args retries remain allowed.
    """
    tool_calls = []

    async def file(**kwargs):
        tool_calls.append(dict(kwargs))
        return "ERR: transient failure"

    stream_round = 0

    async def fake_stream(*args, **kwargs):
        nonlocal stream_round
        stream_round += 1
        if stream_round == 1:
            yield {
                "type": "tool_call",
                "name": "file",
                "args": {"action": "delete", "src": "C:/Users/victim/approved.txt"},
            }
        else:
            yield "The delete could not be completed."

    analysis = _analysis_result()
    replan = AsyncMock(
        return_value='```json\n{"action":"delete","src":"C:/Users/victim/OTHER-FILE.txt"}\n```'
    )
    planner_request = {
        "request_id": "bind-req",
        "tool_name": "file",
        "args": {"action": "delete", "src": "C:/Users/victim/approved.txt"},
        "risk_level": "CRITICAL",
        "status": "pending",
    }
    with (
        patch("backend.brain.reasoning.analysis_pass.run_heuristic_pass", return_value=analysis),
        patch(
            "backend.brain.reasoning.analysis_pass.build_task_graph_if_needed",
            new=AsyncMock(return_value=analysis),
        ),
        patch.object(agent_team, "_fast_route", return_value=["OS_EXECUTOR"]),
        patch.object(agent_team, "_parse_direct_app_action", return_value=None),
        patch.object(agent_team, "_parse_direct_os_action", return_value=None),
        patch.object(agent_team, "get_maya_tools", return_value=[file]),
        patch("backend.skills.skill_watcher.get_dynamic_tools", return_value=[]),
        patch.object(agent_team.tool_planner, "queue_tool", return_value=planner_request),
        patch.object(agent_team.tool_planner, "wait_for_approval", new=AsyncMock(return_value=True)),
        patch.object(agent_team.gemini_adapter, "generate_stream", side_effect=fake_stream),
        patch.object(agent_team.gemini_adapter, "generate_response", new=replan),
    ):
        async for _chunk in agent_team.execute_workflow(
            "approval-binding-session",
            "delete approved.txt",
            [],
        ):
            pass

    assert tool_calls, "the approved tool must execute at least once"
    assert all(
        call == {"action": "delete", "src": "C:/Users/victim/approved.txt"}
        for call in tool_calls
    ), f"approved args drifted: {tool_calls}"
    replan.assert_not_awaited()
