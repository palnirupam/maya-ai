import pytest

from backend.brain.agents import agent_team


def test_parse_direct_app_action_extracts_app_name():
    assert agent_team._parse_direct_app_action("Open koro whatsapp app") == (
        "open_app",
        "whatsapp",
    )
    assert agent_team._parse_direct_app_action("Open notepad") == (
        "open_app",
        "notepad",
    )
    assert agent_team._parse_direct_app_action("Close koro", "whatsapp") == (
        "close_app",
        "whatsapp",
    )
    assert agent_team._parse_direct_app_action("Close", "file explorer") == (
        "close_app",
        "file explorer",
    )
    assert agent_team._parse_direct_app_action("Close koro") == (
        "close_active_window",
        "active window",
    )
    assert agent_team._parse_direct_app_action(
        "vs code baad diye ja ja open ache sob close koro"
    ) == ("close_apps_except", "vs code")
    assert agent_team._parse_direct_app_action(
        "close all apps except visual studio code"
    ) == ("close_apps_except", "visual studio code")
    # "bade" (বাদে = except) is a bare exclusion marker with no trailing "diye".
    # Without it in the parser, "vs code bade sob app close" fell through to
    # close_app("vs code bade sob") and was refused as a protected process.
    assert agent_team._parse_direct_app_action(
        "vs code bade sob app close"
    ) == ("close_apps_except", "vs code")
    assert agent_team._parse_direct_app_action(
        "chrome baade baki sob bondho koro"
    ) == ("close_apps_except", "chrome")
    # Plain "close all apps" (no exception) must map to close_apps_except("") —
    # a broad close-everything — not close_app("all"), which hunted for a
    # process literally named "all" and errored.
    assert agent_team._parse_direct_app_action(
        "please close all apps"
    ) == ("close_apps_except", "")
    assert agent_team._parse_direct_app_action(
        "sob app bondho koro"
    ) == ("close_apps_except", "")
    assert agent_team._parse_direct_app_action("whatsapp e message pathao") is None
    assert agent_team._parse_direct_app_action("app open korte perche na keno") is None
    assert agent_team._parse_direct_app_action("open notepad & calc") is None
    assert agent_team._parse_direct_app_action(
        r"open C:\Windows\System32\notepad.exe"
    ) is None


def test_parse_foreground_youtube_play_intent_preserves_visible_request_query():
    assert agent_team.parse_foreground_youtube_play_intent(
        "Maya yt te cinema chaliye dao"
    ) == "cinema"
    assert agent_team.parse_foreground_youtube_play_intent(
        "YouTube te Dhoom 3 play koro"
    ) == "Dhoom 3"
    assert agent_team.parse_foreground_youtube_play_intent(
        "yt background e gaan chalao"
    ) is None


@pytest.mark.asyncio
async def test_visible_youtube_playback_bypasses_background_audio_and_llm(monkeypatch):
    async def fail_generate_stream(*args, **kwargs):
        raise AssertionError("LLM should not be called for visible YouTube playback")
        yield

    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", fail_generate_stream)
    monkeypatch.setattr(agent_team, "_is_pref_true", lambda key: True)

    calls = []

    def fake_search_youtube(query):
        calls.append(query)
        return "SUCCESS: Opened and focused https://www.youtube.com/watch?v=abc&autoplay=1."

    monkeypatch.setattr(
        "backend.tools.desktop.advanced.browser_tools.search_youtube",
        fake_search_youtube,
    )

    history = []
    first_chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "visible-youtube-session",
            "Maya yt te cinema chaliye dao",
            history,
        )
    ]
    assert calls == []
    assert first_chunks[-1] == (
        "Kon cinema-ta dekhte chao? Naam ta bolo, ami YouTube e screen e open kore chaliye dibo."
    )

    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "visible-youtube-session",
            "Bangla best cinema",
            history,
        )
    ]

    assert calls == ["Bangla best cinema"]
    assert chunks[-1] == "YouTube e 'Bangla best cinema' screen e open kore chaliye dilam."
    assert history[-3] == {
        "role": "tool_call",
        "name": "search_youtube",
        "args": {"query": "Bangla best cinema"},
    }
    assert history[-2]["role"] == "function"
    assert history[-1] == {"role": "assistant", "content": chunks[-1]}


@pytest.mark.asyncio
async def test_simple_open_app_workflow_bypasses_llm(monkeypatch):
    async def fail_generate_stream(*args, **kwargs):
        raise AssertionError("LLM should not be called for simple app open commands")
        yield

    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", fail_generate_stream)

    def fake_open_app(app_name):
        return f"SUCCESS: Launched {app_name}."

    monkeypatch.setattr("backend.tools.desktop.apps.open_app", fake_open_app)

    history = []
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "test-session",
            "Open koro whatsapp app",
            history,
        )
    ]

    assert chunks[-1] == "whatsapp open kore dilam."
    assert history[-3] == {
        "role": "tool_call",
        "name": "open_app",
        "args": {"app_name": "whatsapp"},
    }
    assert history[-2] == {
        "role": "function",
        "name": "open_app",
        "content": "SUCCESS: Launched whatsapp.",
    }
    assert history[-1] == {"role": "assistant", "content": "whatsapp open kore dilam."}


@pytest.mark.asyncio
async def test_simple_close_without_app_name_uses_last_open_app(monkeypatch):
    async def fail_generate_stream(*args, **kwargs):
        raise AssertionError("LLM should not be called for simple app close commands")
        yield

    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", fail_generate_stream)

    def fake_close_app(app_name):
        return f"SUCCESS: Closed {app_name}."

    monkeypatch.setattr("backend.tools.desktop.apps.close_app", fake_close_app)

    history = [
        {
            "role": "tool_call",
            "name": "open_app",
            "args": {"app_name": "whatsapp"},
        },
        {
            "role": "function",
            "name": "open_app",
            "content": "SUCCESS: Launched whatsapp via protocol.",
        },
    ]
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "test-session",
            "Close koro",
            history,
        )
    ]

    assert chunks[-1] == "whatsapp close kore dilam."
    assert history[-1] == {"role": "assistant", "content": "whatsapp close kore dilam."}


@pytest.mark.asyncio
async def test_direct_close_surfaces_unverified_partial_result(monkeypatch):
    async def fail_generate_stream(*args, **kwargs):
        raise AssertionError("LLM should not be called for a direct app close")
        yield

    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", fail_generate_stream)
    monkeypatch.setattr(
        "backend.tools.desktop.apps.close_app",
        lambda app_name: (
            f"PARTIAL: Requested close for {app_name}, but 1 matching window(s) remain open."
        ),
    )

    history = []
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "partial-close-session",
            "Close notepad",
            history,
        )
    ]

    assert "close kore dilam" not in chunks[-1]
    assert "PARTIAL:" in chunks[-1]
    assert history[-2]["role"] == "function"
    assert history[-2]["content"].startswith("PARTIAL:")


@pytest.mark.asyncio
async def test_direct_app_exception_is_truthful_and_audited(monkeypatch):
    async def fail_generate_stream(*args, **kwargs):
        raise AssertionError("LLM should not be called for a direct app action")
        yield

    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", fail_generate_stream)
    monkeypatch.setattr(agent_team, "_is_pref_true", lambda key: True)

    def broken_open(app_name):
        raise RuntimeError("launcher unavailable")

    monkeypatch.setattr("backend.tools.desktop.apps.open_app", broken_open)

    from backend.system.observability import observability

    metrics = []

    async def capture_metric(item):
        metrics.append(item)

    monkeypatch.setattr(observability, "log", capture_metric)

    history = []
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "app-exception-session",
            "Open notepad",
            history,
        )
    ]

    assert "open kore dilam" not in chunks[-1]
    assert "ERROR:" in chunks[-1]
    assert history[-3] == {
        "role": "tool_call",
        "name": "open_app",
        "args": {"app_name": "notepad"},
    }
    assert history[-2]["role"] == "function"
    assert history[-2]["content"].startswith("ERROR:")
    assert history[-1] == {"role": "assistant", "content": chunks[-1]}
    assert len(metrics) == 1
    assert metrics[0].session_id == "app-exception-session"
    assert metrics[0].tool_calls == ["open_app"]
    assert metrics[0].error == "ERROR"


@pytest.mark.asyncio
async def test_bare_close_after_open_uses_same_app_without_llm(monkeypatch):
    async def fail_generate_response(*args, **kwargs):
        raise AssertionError("Router LLM should not be called for a remembered app close")

    async def fail_generate_stream(*args, **kwargs):
        raise AssertionError("Agent LLM should not be called for a remembered app close")
        yield

    monkeypatch.setattr(agent_team.gemini_adapter, "generate_response", fail_generate_response)
    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", fail_generate_stream)

    calls = []

    def fake_close_app(app_name):
        calls.append(app_name)
        return f"SUCCESS: Closed {app_name}."

    monkeypatch.setattr("backend.tools.desktop.apps.close_app", fake_close_app)

    history = [
        {"role": "user", "content": "File explorer open koro"},
        {
            "role": "tool_call",
            "name": "open_app",
            "args": {"app_name": "file explorer"},
        },
        {
            "role": "function",
            "name": "open_app",
            "content": "SUCCESS: Launched file explorer.",
        },
        {"role": "assistant", "content": "file explorer open kore dilam."},
        {"role": "user", "content": "Close"},
    ]
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "telegram-followup-session",
            "Close",
            history,
        )
    ]

    assert calls == ["file explorer"]
    assert chunks[-1] == "file explorer close kore dilam."
    assert history[-3] == {
        "role": "tool_call",
        "name": "close_app",
        "args": {"app_name": "file explorer"},
    }
    assert history[-2] == {
        "role": "function",
        "name": "close_app",
        "content": "SUCCESS: Closed file explorer.",
    }
    assert history[-1] == {
        "role": "assistant",
        "content": "file explorer close kore dilam.",
    }


@pytest.mark.asyncio
async def test_simple_close_without_history_closes_active_window(monkeypatch):
    async def fail_generate_stream(*args, **kwargs):
        raise AssertionError("LLM should not be called for simple active-window close commands")
        yield

    monkeypatch.setattr(agent_team, "_LAST_DIRECT_APP_NAME", None)
    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", fail_generate_stream)

    def fake_close_active_window():
        return "SUCCESS: Closed active window: WhatsApp."

    monkeypatch.setattr("backend.tools.desktop.apps.close_active_window", fake_close_active_window)

    history = []
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "test-session",
            "Close koro",
            history,
        )
    ]

    assert chunks[-1] == "active window close kore dilam."
    assert history[-1] == {"role": "assistant", "content": "active window close kore dilam."}


@pytest.mark.asyncio
async def test_close_all_except_workflow_bypasses_llm(monkeypatch):
    async def fail_generate_stream(*args, **kwargs):
        raise AssertionError("LLM should not be called for close-all-except commands")
        yield

    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", fail_generate_stream)
    monkeypatch.setattr(agent_team, "_is_pref_true", lambda key: True)
    monkeypatch.setattr(
        agent_team.tool_planner,
        "queue_tool",
        lambda name, payload, risk_level: {
            "request_id": "bulk-close-request",
            "tool_name": name,
            "payload": payload,
            "risk_level": "HIGH",
        },
    )

    async def approve(_request_id):
        return True

    monkeypatch.setattr(agent_team.tool_planner, "wait_for_approval", approve)

    calls = []

    def fake_close_apps_except(excluded_apps):
        calls.append(excluded_apps)
        return "SUCCESS: Closed 2 app window(s). Kept open: vs code."

    monkeypatch.setattr("backend.tools.desktop.apps.close_apps_except", fake_close_apps_except)

    history = []
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "bulk-close-session",
            "vs code baad diye ja ja open ache sob close koro",
            history,
        )
    ]

    assert calls == ["vs code"]
    assert chunks[-1] == "vs code open rekhe baki app gulo close kore dilam."
    assert history[-2] == {
        "role": "function",
        "name": "close_apps_except",
        "content": "SUCCESS: Closed 2 app window(s). Kept open: vs code.",
    }


@pytest.mark.asyncio
async def test_close_all_except_requires_approval(monkeypatch):
    monkeypatch.setattr(agent_team, "_is_pref_true", lambda key: True)
    monkeypatch.setattr(
        agent_team.tool_planner,
        "queue_tool",
        lambda name, payload, risk_level: {
            "request_id": "denied-bulk-close",
            "tool_name": name,
            "payload": payload,
            "risk_level": "HIGH",
        },
    )

    async def deny(_request_id):
        return False

    monkeypatch.setattr(agent_team.tool_planner, "wait_for_approval", deny)
    monkeypatch.setattr(
        "backend.tools.desktop.apps.close_apps_except",
        lambda excluded_apps: pytest.fail("broad close executed without approval"),
    )

    history = []
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "denied-bulk-close-session",
            "close all apps except visual studio code",
            history,
        )
    ]

    requests = [chunk for chunk in chunks if isinstance(chunk, dict)]
    assert requests[-1]["type"] == "tool_call_request"
    assert requests[-1]["data"]["payload"] == {
        "excluded_apps": "visual studio code"
    }
    assert chunks[-1] == "Approval na paoway baki app gulo close kora hoyni."
    assert history[-2]["content"].startswith("Permission denied:")


@pytest.mark.asyncio
async def test_direct_app_fast_path_respects_system_permission(monkeypatch):
    monkeypatch.setattr(agent_team, "_is_pref_true", lambda key: False)
    monkeypatch.setattr(
        "backend.tools.desktop.apps.open_app",
        lambda app_name: pytest.fail("app tool bypassed PERM_SYSTEM"),
    )

    async def disabled_reply(*args, **kwargs):
        yield "System controls are disabled."

    monkeypatch.setattr(agent_team.gemini_adapter, "generate_stream", disabled_reply)

    history = []
    chunks = [
        chunk
        async for chunk in agent_team.execute_workflow(
            "app-permission-off",
            "Open notepad",
            history,
        )
    ]

    assert chunks[-1] == "System controls are disabled."
