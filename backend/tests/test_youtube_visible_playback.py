from backend.tools.desktop.advanced import browser_tools


def test_open_youtube_foreground_confirms_active_youtube_window(monkeypatch):
    monkeypatch.setattr(
        browser_tools,
        "open_url",
        lambda url: f"SUCCESS: Opened {url} in the default browser.",
    )
    monkeypatch.setattr(
        "backend.tools.desktop.apps.focus_app",
        lambda app_name: "SUCCESS: Focused window 'Cinema - YouTube - Google Chrome'.",
    )

    result = browser_tools._open_youtube_foreground("https://www.youtube.com/watch?v=abc")

    assert result == "SUCCESS: Opened and focused https://www.youtube.com/watch?v=abc."


def test_open_youtube_foreground_does_not_claim_success_without_focus(monkeypatch):
    monkeypatch.setattr(
        browser_tools,
        "open_url",
        lambda url: f"SUCCESS: Opened {url} in the default browser.",
    )
    monkeypatch.setattr(
        "backend.tools.desktop.apps.focus_app",
        lambda app_name: "PARTIAL: Requested focus but it did not become active.",
    )

    result = browser_tools._open_youtube_foreground("https://www.youtube.com/watch?v=abc")

    assert result.startswith("PARTIAL:")
    assert "could not focus the YouTube window" in result
