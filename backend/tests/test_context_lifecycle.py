from unittest.mock import AsyncMock, patch

import pytest

from backend.brain.agents import agent_team
from backend.brain.budget_manager import budget_manager
from backend.brain.memory.context_condenser import (
    CONDENSE_THRESHOLD,
    SUMMARY_FLAG,
    ContextCondenser,
    _condensers,
    get_condenser,
)
from backend.brain.orchestrator import ConversationOrchestrator
from backend.brain.providers.gemini_adapter import clean_context


def _history(turns: int, *, include_tools: bool = False) -> list[dict]:
    history = [{"role": "system", "content": "primary system prompt"}]
    for index in range(turns):
        history.append({"role": "user", "content": f"user {index}"})
        if include_tools:
            history.extend([
                {
                    "role": "tool_call",
                    "name": "file",
                    "args": {"action": "read", "src": f"C:/file-{index}.txt"},
                },
                {
                    "role": "function",
                    "name": "file",
                    "content": f"result {index}",
                },
            ])
        history.append({"role": "assistant", "content": f"assistant {index}"})
    return history


@pytest.mark.asyncio
async def test_condenser_is_reachable_and_preserves_complete_recent_turns() -> None:
    condenser = ContextCondenser()
    history = _history(CONDENSE_THRESHOLD + 1, include_tools=True)

    assert condenser.needs_condensing(history)
    with patch.object(
        condenser,
        "_summarize",
        new=AsyncMock(return_value="older turns summarized"),
    ):
        condensed = await condenser.condense(history)

    assert condensed[0] == history[0]
    assert condensed[1][SUMMARY_FLAG] is True
    assert sum(message.get("role") == "user" for message in condensed) == 8
    assert sum(message.get("role") == "tool_call" for message in condensed) == 8
    assert sum(message.get("role") == "function" for message in condensed) == 8
    assert condensed[2]["role"] == "user"


@pytest.mark.asyncio
async def test_condenser_rolls_prior_summary_forward_without_duplicates() -> None:
    condenser = ContextCondenser()
    first_history = _history(CONDENSE_THRESHOLD + 1)

    summarize = AsyncMock(side_effect=["summary one", "summary two"])
    with patch.object(condenser, "_summarize", new=summarize):
        first = await condenser.condense(first_history)
        extended = first + _history(6)[1:]
        second = await condenser.condense(extended)

    summaries = [message for message in second if message.get(SUMMARY_FLAG)]
    assert len(summaries) == 1
    assert summaries[0]["content"].endswith("summary two")
    second_summary_input = summarize.await_args_list[1].args[0]
    assert any(message.get(SUMMARY_FLAG) for message in second_summary_input)


def test_agent_context_receives_rolling_summary() -> None:
    config = agent_team.AGENTS["CHAT"]
    history = [
        {"role": "system", "content": "primary"},
        {
            "role": "system",
            "content": "[Conversation Summary - earlier turns condensed]\nuser likes concise replies",
            SUMMARY_FLAG: True,
        },
        {"role": "user", "content": "hello"},
    ]

    context = agent_team._build_agent_context(
        config,
        history,
        [],
        "hello",
        "professional",
        "concise",
        "\nclock",
        "english",
    )

    assert "user likes concise replies" in context[0]["content"]


def test_clean_context_preserves_primary_prompt_and_summary_order() -> None:
    context = clean_context([
        {"role": "system", "content": "primary prompt"},
        {"role": "system", "content": "rolling summary"},
        {"role": "user", "content": "hello"},
    ])

    assert [message["content"] for message in context[:2]] == [
        "primary prompt",
        "rolling summary",
    ]


def test_release_session_clears_only_ephemeral_state() -> None:
    session_id = "ephemeral-websocket-session"
    orchestrator = ConversationOrchestrator()
    orchestrator.sessions[session_id] = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "persisted elsewhere"},
    ]
    get_condenser(session_id)
    budget_manager.set_requested_tier(session_id, "reasoning")
    agent_team._remember_last_agent(session_id, "OS_EXECUTOR")
    agent_team._remember_direct_app(session_id, "notepad")
    agent_team._remember_os_control(session_id, "volume")
    agent_team._remember_pending_send(session_id)

    with patch.object(orchestrator, "_persist_session_memory") as persist:
        assert orchestrator.release_session(session_id)

    persist.assert_not_called()
    assert session_id not in orchestrator.sessions
    assert session_id not in _condensers
    assert session_id not in budget_manager._sessions
    assert session_id not in agent_team._LAST_AGENT_BY_SESSION
    assert session_id not in agent_team._LAST_DIRECT_APP_BY_SESSION
    assert session_id not in agent_team._LAST_OS_CONTROL_BY_SESSION
    assert session_id not in agent_team._PENDING_SEND_BY_SESSION


def test_direct_app_followup_state_is_isolated_per_session() -> None:
    agent_team._remember_direct_app("session-a", "notepad")
    agent_team._remember_direct_app("session-b", "calculator")
    try:
        assert agent_team._last_app_from_history([], "session-a") == "notepad"
        assert agent_team._last_app_from_history([], "session-b") == "calculator"
    finally:
        agent_team.evict_session_state("session-a")
        agent_team.evict_session_state("session-b")
