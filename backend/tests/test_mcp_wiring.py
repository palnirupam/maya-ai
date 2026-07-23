from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.brain.agents import agent_team
from backend.brain.providers.gemini_adapter import (
    convert_tools_to_anthropic_tools,
    convert_tools_to_gemini_tools,
    convert_tools_to_openai_tools,
)
from backend.brain.reasoning.analysis_pass import AnalysisResult
from backend.tools.mcp_service import (
    MAX_GEMINI_TOOLS,
    MCPService,
    ServerState,
)


@pytest.mark.asyncio
async def test_mcp_discovery_returns_provider_neutral_schema() -> None:
    service = MCPService()
    service.servers["demo"] = SimpleNamespace(
        state=ServerState.READY,
        config=SimpleNamespace(max_tools=5, priority=10),
        name="demo",
        _tools=[
            SimpleNamespace(
                name="lookup",
                description="Look up a demo record",
                inputSchema={
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            )
        ],
    )

    tools = await service.get_available_tools(limit=5)

    assert tools == [
        {
            "name": "demo__lookup",
            "description": "Look up a demo record",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
    ]


def test_mcp_schema_converts_for_all_supported_provider_formats() -> None:
    schema = {
        "name": "demo__lookup",
        "description": "Look up a demo record",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }

    gemini_tool = convert_tools_to_gemini_tools([schema])[0]
    declaration = gemini_tool.function_declarations[0]
    assert declaration.name == "demo__lookup"
    assert declaration.parameters.required == ["query"]

    openai_tool = convert_tools_to_openai_tools([schema])[0]
    assert openai_tool["function"]["name"] == "demo__lookup"
    assert openai_tool["function"]["parameters"] == schema["parameters"]

    anthropic_tool = convert_tools_to_anthropic_tools([schema])[0]
    assert anthropic_tool["name"] == "demo__lookup"
    assert anthropic_tool["input_schema"] == schema["parameters"]


def test_mcp_merge_preserves_native_routing_and_honors_tool_cap() -> None:
    def native_lookup() -> None:
        pass

    duplicate_schema = {
        "name": "native_lookup",
        "description": "Must not replace the native function",
        "parameters": {"type": "object", "properties": {}},
    }
    mcp_schema = {
        "name": "demo__lookup",
        "description": "Look up a demo record",
        "parameters": {"type": "object", "properties": {}},
    }
    over_cap_schema = {
        "name": "demo__second_lookup",
        "description": "Must be excluded by the provider cap",
        "parameters": {"type": "object", "properties": {}},
    }

    merged = agent_team._merge_mcp_tool_schemas(
        [native_lookup],
        [duplicate_schema, mcp_schema, over_cap_schema],
        max_total=2,
    )

    assert merged == [native_lookup, mcp_schema]


def _analysis_result() -> AnalysisResult:
    return AnalysisResult(
        complexity_score=1,
        model_tier="fast",
        fast_path_eligible=True,
        needs_task_graph=False,
        task_graph=None,
    )


@pytest.mark.asyncio
async def test_streaming_agent_exposes_and_executes_mcp_tool() -> None:
    mcp_schema = {
        "name": "demo__lookup",
        "description": "Look up a demo record",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    captured_tool_sets = []
    stream_round = 0

    async def fake_stream(*args, **kwargs):
        nonlocal stream_round
        captured_tool_sets.append(kwargs["override_tools"])
        stream_round += 1
        if stream_round == 1:
            yield {
                "type": "tool_call",
                "name": "demo__lookup",
                "args": {"query": "maya"},
            }
        else:
            yield "MCP lookup complete."

    analysis = _analysis_result()
    call_tool = AsyncMock(return_value="record: maya")
    planner = MagicMock()
    planner.queue_tool.return_value = {
        "request_id": "mcp-approval",
        "tool_name": "demo__lookup",
        "risk_level": "HIGH",
    }
    planner.wait_for_approval = AsyncMock(return_value=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with (
        patch("backend.brain.reasoning.analysis_pass.run_heuristic_pass", return_value=analysis),
        patch(
            "backend.brain.reasoning.analysis_pass.build_task_graph_if_needed",
            new=AsyncMock(return_value=analysis),
        ),
        patch.object(agent_team, "_fast_route", return_value=["OS_EXECUTOR"]),
        patch.object(agent_team, "_parse_direct_app_action", return_value=None),
        patch.object(agent_team, "_parse_direct_os_action", return_value=None),
        patch.object(agent_team, "get_maya_tools", return_value=[]),
        patch("backend.skills.skill_watcher.get_dynamic_tools", return_value=[]),
        patch(
            "backend.tools.mcp_service.mcp_service.get_available_tools",
            new=AsyncMock(return_value=[mcp_schema]),
        ) as discover,
        patch(
            "backend.tools.mcp_service.mcp_service.call_tool",
            new=call_tool,
        ),
        patch("backend.database.connection.SessionLocal", return_value=db),
        patch.object(agent_team, "tool_planner", planner),
        patch.object(agent_team.gemini_adapter, "generate_stream", side_effect=fake_stream),
    ):
        chunks = [
            chunk
            async for chunk in agent_team.execute_workflow(
                "mcp-stream-session",
                "Use the demo MCP lookup for Maya",
                [],
            )
        ]

    discover.assert_awaited_once_with(limit=MAX_GEMINI_TOOLS)
    planner.queue_tool.assert_called_once_with(
        "demo__lookup", {"query": "maya"}, risk_level="danger"
    )
    planner.wait_for_approval.assert_awaited_once_with("mcp-approval")
    call_tool.assert_awaited_once_with("demo__lookup", {"query": "maya"})
    assert captured_tool_sets
    assert all(mcp_schema in tool_set for tool_set in captured_tool_sets)
    assert "MCP lookup complete." in "".join(
        chunk for chunk in chunks if isinstance(chunk, str)
    )


@pytest.mark.asyncio
async def test_mcp_discovery_failure_does_not_break_normal_agent_turn() -> None:
    analysis = _analysis_result()

    async def fake_stream(*args, **kwargs):
        yield "Normal response."

    with (
        patch("backend.brain.reasoning.analysis_pass.run_heuristic_pass", return_value=analysis),
        patch(
            "backend.brain.reasoning.analysis_pass.build_task_graph_if_needed",
            new=AsyncMock(return_value=analysis),
        ),
        patch.object(agent_team, "_fast_route", return_value=["CHAT"]),
        patch.object(agent_team, "get_maya_tools", return_value=[]),
        patch("backend.skills.skill_watcher.get_dynamic_tools", return_value=[]),
        patch(
            "backend.tools.mcp_service.mcp_service.get_available_tools",
            new=AsyncMock(side_effect=RuntimeError("MCP offline")),
        ),
        patch.object(agent_team.gemini_adapter, "generate_stream", side_effect=fake_stream),
    ):
        chunks = [
            chunk
            async for chunk in agent_team.execute_workflow(
                "mcp-offline-session",
                "hello",
                [],
            )
        ]

    assert "Normal response." in "".join(
        chunk for chunk in chunks if isinstance(chunk, str)
    )
