from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.brain.agents import agent_team
from backend.brain.reasoning.analysis_pass import AnalysisResult
from backend.tools.unified.dispatchers.file_router import file


def _analysis_result() -> AnalysisResult:
    return AnalysisResult(
        complexity_score=1,
        model_tier="fast",
        fast_path_eligible=True,
        needs_task_graph=False,
        task_graph=None,
    )


def _workflow_patches(stream, planner):
    analysis = _analysis_result()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return (
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
        patch.object(agent_team.gemini_adapter, "generate_stream", side_effect=stream),
        patch.object(agent_team, "tool_planner", planner),
        patch("backend.database.connection.SessionLocal", return_value=db),
    )


@pytest.mark.asyncio
async def test_approved_delete_by_name_executes_and_reports_verified_result(
    tmp_path, monkeypatch
):
    target = tmp_path / "audit-delete.txt"
    target.write_text("temporary", encoding="utf-8")
    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.find_items",
        lambda name, n: [str(target)],
    )
    planner = MagicMock()
    planner.queue_tool.return_value = {
        "request_id": "r02-delete-by-name",
        "tool_name": "file",
        "payload": {"action": "delete_by_name", "name": "audit-delete.txt", "n": 1},
        "risk_level": "CRITICAL",
    }
    planner.wait_for_approval = AsyncMock(return_value=True)
    rounds = 0

    async def stream(*args, **kwargs):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            yield {
                "type": "tool_call",
                "name": "file",
                "args": {"action": "delete_by_name", "name": "audit-delete.txt", "n": 1},
            }
        else:
            yield "Deleted the approved temporary file."

    patches = _workflow_patches(stream, planner)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
        history = []
        chunks = [
            chunk
            async for chunk in agent_team.execute_workflow(
                "r02-approved-delete", "Delete audit-delete.txt", history
            )
        ]

    request = next(chunk for chunk in chunks if isinstance(chunk, dict) and chunk.get("type") == "tool_call_request")
    assert request["data"]["payload"]["action"] == "delete_by_name"
    planner.wait_for_approval.assert_awaited_once_with("r02-delete-by-name")
    assert not target.exists()
    result = next(item for item in history if item.get("role") == "function")
    assert result["content"].startswith("Deleted 1:")
    assert "Deleted the approved temporary file." in chunks


@pytest.mark.asyncio
async def test_organize_executes_without_destructive_approval_and_reports_result(tmp_path):
    (tmp_path / "photo.jpg").write_text("image", encoding="utf-8")
    (tmp_path / "report.pdf").write_text("document", encoding="utf-8")
    planner = MagicMock()
    rounds = 0

    async def stream(*args, **kwargs):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            yield {
                "type": "tool_call",
                "name": "file",
                "args": {"action": "organize", "path": str(tmp_path)},
            }
        else:
            yield "Organized the temporary folder."

    patches = _workflow_patches(stream, planner)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
        history = []
        chunks = [
            chunk
            async for chunk in agent_team.execute_workflow(
                "r02-organize", "Organize this temporary folder", history
            )
        ]

    planner.queue_tool.assert_not_called()
    assert (tmp_path / "Images" / "photo.jpg").is_file()
    assert (tmp_path / "Documents" / "report.pdf").is_file()
    result = next(item for item in history if item.get("role") == "function")
    assert "Organized 2 files" in result["content"]
    assert "Organized the temporary folder." in chunks


@pytest.mark.asyncio
async def test_search_executes_without_approval_and_preserves_exact_result_path(
    tmp_path, monkeypatch
):
    target = tmp_path / "audit-search-report.txt"
    target.write_text("temporary", encoding="utf-8")
    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.find_items",
        lambda name, n: [str(target)],
    )
    planner = MagicMock()
    rounds = 0

    async def stream(*args, **kwargs):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            yield {
                "type": "tool_call",
                "name": "file",
                "args": {"action": "search", "name": "audit-search-report.txt", "n": 5},
            }
        else:
            yield f"Found the report at {target}."

    patches = _workflow_patches(stream, planner)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
        history = []
        chunks = [
            chunk
            async for chunk in agent_team.execute_workflow(
                "r02-search", "Find audit-search-report.txt", history
            )
        ]

    planner.queue_tool.assert_not_called()
    result = next(item for item in history if item.get("role") == "function")
    assert result["content"] == f"Found 1:\n  - {target}"
    assert f"Found the report at {target}." in chunks
