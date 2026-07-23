from types import SimpleNamespace
from unittest.mock import patch

import psutil
import pytest

from backend.tools.desktop import apps, shortcuts
from backend.tools.desktop.advanced import computer_use


def test_normalize_app_query_accepts_whatsapp_typo_and_command_words():
    assert apps._normalize_app_query("whatapp open koro") == "whatsapp"
    assert apps._normalize_app_query("open app") == ""


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "notepad & calc",
        "notepad; calc",
        "notepad | calc",
        "notepad $(calc)",
        r"C:\Windows\System32\notepad.exe",
    ],
)
def test_app_controls_reject_shell_syntax_and_paths(unsafe_name, monkeypatch):
    monkeypatch.setattr(
        apps,
        "_popen",
        lambda *args, **kwargs: pytest.fail("unsafe app input reached process launch"),
    )

    assert apps.open_app(unsafe_name).startswith("ERROR:")
    assert apps.close_app(unsafe_name).startswith("ERROR:")
    assert apps.focus_app(unsafe_name).startswith("ERROR:")


def test_open_app_uses_start_apps_for_store_apps_when_protocol_fails():
    with (
        patch.object(apps, "_launch_protocol", return_value=False),
        patch.object(
            apps,
            "_launch_start_app",
            return_value="SUCCESS: Launched WhatsApp from Windows Start Apps.",
        ) as start_app,
        patch.object(apps, "_launch_start_menu_shortcut", return_value=None),
        patch.object(apps, "_launch_via_windows_search") as search,
    ):
        result = apps.open_app("whatapp open koro")

    assert result == "SUCCESS: Launched WhatsApp from Windows Start Apps."
    start_app.assert_called_once_with("whatsapp", "WhatsApp")
    search.assert_not_called()


def test_open_app_uses_whatsapp_web_when_native_launchers_are_missing():
    with (
        patch.object(apps, "_launch_protocol", return_value=False),
        patch.object(apps, "_launch_start_app", return_value=None),
        patch.object(apps, "_launch_start_menu_shortcut", return_value=None),
        patch("webbrowser.open", return_value=True) as open_browser,
        patch.object(apps, "_launch_via_windows_search") as search,
    ):
        result = apps.open_app("whatsapp")

    assert result == "SUCCESS: Opened whatsapp in browser fallback."
    open_browser.assert_called_once_with("https://web.whatsapp.com/")
    search.assert_not_called()


def test_open_app_falls_back_to_windows_search_for_unknown_apps():
    with (
        patch.object(apps, "_launch_start_app", return_value=None),
        patch.object(apps, "_launch_start_menu_shortcut", return_value=None),
        patch.object(
            apps,
            "_launch_via_windows_search",
            return_value="SUCCESS: Searched and opened figma via Windows Search.",
        ) as search,
    ):
        result = apps.open_app("figma open koro")

    assert result == "SUCCESS: Searched and opened figma via Windows Search."
    search.assert_called_once_with("figma")


def test_background_app_open_delegates_to_open_app():
    with (
        patch("backend.tools.desktop.apps.open_app", return_value="SUCCESS: Launched figma") as open_app,
        patch.object(computer_use.time, "sleep"),
    ):
        result = computer_use._background_app_control_sync("figma", "open")

    assert result == "SUCCESS: Launched figma"
    open_app.assert_called_once_with("figma")


def test_focus_app_waits_for_new_window_and_verifies_activation(monkeypatch):
    calls = 0
    target = SimpleNamespace(
        title="Untitled - Notepad",
        _hWnd=610,
        isMinimized=False,
        activate=lambda: None,
    )

    def get_windows():
        nonlocal calls
        calls += 1
        return [] if calls < 3 else [target]

    fake_gw = SimpleNamespace(
        getAllWindows=get_windows,
        getActiveWindow=lambda: target,
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)

    result = apps.focus_app("notepad")

    assert result == "SUCCESS: Focused window 'Untitled - Notepad'."
    assert calls >= 3


def test_focus_app_reports_partial_when_activation_is_not_observed(monkeypatch):
    target = SimpleNamespace(
        title="Untitled - Notepad",
        _hWnd=611,
        isMinimized=False,
        activate=lambda: None,
    )
    other = SimpleNamespace(title="Other app", _hWnd=612)
    fake_gw = SimpleNamespace(
        getAllWindows=lambda: [target],
        getActiveWindow=lambda: other,
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(
        apps,
        "_wait_for_active_window",
        lambda gw, window: False,
    )

    result = apps.focus_app("notepad")

    assert result == (
        "PARTIAL: Requested focus for window 'Untitled - Notepad', "
        "but it did not become the active window."
    )


def test_close_app_closes_matching_window_title(monkeypatch):
    closed = []
    fake_window = SimpleNamespace(
        title="WhatsApp - Google Chrome",
        close=lambda: (closed.append("window"), fake_windows.remove(fake_window)),
    )
    fake_windows = [fake_window]
    fake_gw = SimpleNamespace(getAllWindows=lambda: fake_windows)

    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [])

    result = apps.close_app("whatsapp")

    assert result.startswith("SUCCESS: Closed window(s): WhatsApp")
    assert closed == ["window"]


def test_close_app_reports_partial_when_window_remains_open(monkeypatch):
    fake_window = SimpleNamespace(title="Untitled - Notepad", close=lambda: None)
    fake_gw = SimpleNamespace(getAllWindows=lambda: [fake_window])

    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [])
    monkeypatch.setattr(apps, "_wait_for_matching_windows", lambda gw, predicate: [fake_window.title])

    result = apps.close_app("notepad")

    assert result.startswith("PARTIAL: Requested close")
    assert "remain open" in result


def test_close_app_refuses_window_owned_by_runtime_host(monkeypatch):
    protected = SimpleNamespace(
        title="Project - Visual Studio Code",
        _hWnd=501,
        close=lambda: pytest.fail("protected host window must not be closed"),
    )
    fake_gw = SimpleNamespace(getAllWindows=lambda: [protected])

    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(apps, "_window_is_protected_runtime", lambda window: True)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [])

    result = apps.close_app("visual studio code")

    assert result.startswith("ERROR: Refused to close")
    assert "protected Maya/runtime process" in result


def test_close_app_falls_back_to_taskkill_when_process_kill_is_denied(monkeypatch):
    class FakeProc:
        pid = 188
        info = {"pid": 188, "name": "WhatsApp.exe"}

        def parent(self):
            return SimpleNamespace(pid=1234)

        def username(self):
            return "DESKTOP-ABC\\user"

        def terminate(self):
            raise psutil.AccessDenied(pid=self.pid, name=self.info["name"])

    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", None)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [FakeProc()])

    taskkill_calls = []

    def fake_run(args, **kwargs):
        taskkill_calls.append(args)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(apps.subprocess, "run", fake_run)
    monkeypatch.setattr(apps, "_wait_for_process_exit", lambda proc: True)

    result = apps.close_app("whatsapp")

    assert result == "SUCCESS: Closed WhatsApp.exe."
    assert taskkill_calls == [["taskkill", "/F", "/T", "/PID", "188"]]


def test_close_app_forces_and_verifies_stubborn_process(monkeypatch):
    class FakeProc:
        pid = 189
        info = {"pid": 189, "name": "Notepad.exe"}

        def parent(self):
            return SimpleNamespace(pid=1234)

        def username(self):
            return "DESKTOP-ABC\\user"

        def terminate(self):
            return None

    proc = FakeProc()
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", None)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [proc])
    monkeypatch.setattr(apps, "_is_protected_runtime_process", lambda item: False)

    exit_checks = iter([False, True])
    monkeypatch.setattr(
        apps,
        "_wait_for_process_exit",
        lambda item: next(exit_checks),
    )
    monkeypatch.setattr(
        apps.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    assert apps.close_app("notepad") == "SUCCESS: Closed Notepad.exe."


def test_close_app_does_not_claim_success_when_forced_process_remains(monkeypatch):
    class FakeProc:
        pid = 190
        info = {"pid": 190, "name": "Notepad.exe"}

        def parent(self):
            return SimpleNamespace(pid=1234)

        def username(self):
            return "DESKTOP-ABC\\user"

        def terminate(self):
            return None

    proc = FakeProc()
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", None)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [proc])
    monkeypatch.setattr(apps, "_is_protected_runtime_process", lambda item: False)
    monkeypatch.setattr(apps, "_wait_for_process_exit", lambda item: False)
    monkeypatch.setattr(
        apps.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    result = apps.close_app("notepad")

    assert result.startswith("ERROR:")
    assert "still running after forced close" in result


def test_close_apps_except_preserves_vscode_and_closes_other_windows(monkeypatch):
    closed = []

    def window(title):
        return SimpleNamespace(title=title, close=lambda: closed.append(title))

    windows = [
        window("agent_team.py - maya-ai - Visual Studio Code"),
        window("WhatsApp"),
        window("Settings"),
        window("Maya AI"),
        window("Program Manager"),
        window(""),
    ]
    fake_gw = SimpleNamespace(
        getAllWindows=lambda: [item for item in windows if item.title not in closed]
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)

    result = apps.close_apps_except("vs code")

    assert closed == ["WhatsApp", "Settings"]
    assert result.startswith("SUCCESS: Closed 2 app window(s): WhatsApp, Settings.")
    assert "Kept open: vs code." in result


def test_close_apps_except_keeps_runtime_host_when_not_excluded(monkeypatch):
    closed = []

    def window(title):
        return SimpleNamespace(title=title, close=lambda: closed.append(title))

    host = window("RELIABILITY_AUDIT.md - Visual Studio Code")
    whatsapp = window("WhatsApp")
    windows = [host, whatsapp]
    fake_gw = SimpleNamespace(
        getAllWindows=lambda: [item for item in windows if item.title not in closed]
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(
        apps,
        "_window_is_protected_runtime",
        lambda item: item is host,
    )

    result = apps.close_apps_except("notepad")

    assert closed == ["WhatsApp"]
    assert result.startswith("SUCCESS: Closed 1 app window(s): WhatsApp.")
    assert "Protected Maya/runtime windows kept open: 1." in result


def test_close_apps_except_empty_closes_all_but_keeps_protected(monkeypatch):
    # Plain "close all apps" (no exception) maps to close_apps_except("") — every
    # non-protected window closes while Maya/runtime host windows stay open.
    closed = []

    def window(title):
        return SimpleNamespace(title=title, close=lambda: closed.append(title))

    host = window("agent_team.py - Visual Studio Code")
    windows = [window("WhatsApp"), window("Settings"), host, window("Maya AI")]
    fake_gw = SimpleNamespace(
        getAllWindows=lambda: [item for item in windows if item.title not in closed]
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(apps, "_window_is_protected_runtime", lambda item: item is host)

    result = apps.close_apps_except("")

    assert closed == ["WhatsApp", "Settings"]  # "Maya AI" kept by protected title
    assert result.startswith("SUCCESS: Closed 2 app window(s): WhatsApp, Settings.")
    assert "Protected Maya/runtime windows kept open: 1." in result


def test_close_apps_except_reports_partial_when_a_window_remains(monkeypatch):
    stubborn = SimpleNamespace(title="Unsaved - Notepad", close=lambda: None)
    fake_gw = SimpleNamespace(getAllWindows=lambda: [stubborn])
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(apps, "_wait_for_matching_windows", lambda gw, predicate: [stubborn.title])

    result = apps.close_apps_except("vs code")

    assert result.startswith("ERROR: Could not close app windows:")
    assert "still open after close request" in result


def test_close_active_window_reports_partial_when_window_remains(monkeypatch):
    stubborn = SimpleNamespace(title="Unsaved - Notepad", close=lambda: None)
    fake_gw = SimpleNamespace(
        getActiveWindow=lambda: stubborn,
        getAllWindows=lambda: [stubborn],
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(apps, "_wait_for_matching_windows", lambda gw, predicate: [stubborn.title])

    result = apps.close_active_window()

    assert result == (
        "PARTIAL: Requested close for active window 'Unsaved - Notepad', "
        "but it remains open."
    )


def test_close_verification_waits_for_window_to_disappear(monkeypatch):
    calls = 0
    closing = SimpleNamespace(title="Untitled - Notepad", close=lambda: None)

    def get_windows():
        nonlocal calls
        calls += 1
        return [closing] if calls == 1 else []

    fake_gw = SimpleNamespace(getAllWindows=get_windows)
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [])

    result = apps.close_app("notepad")

    assert result.startswith("SUCCESS: Closed window(s):")
    assert calls >= 2


def test_close_app_refuses_maya_target(monkeypatch):
    monkeypatch.setattr(
        psutil,
        "process_iter",
        lambda attrs: (_ for _ in ()).throw(AssertionError("processes must not be inspected")),
    )

    assert apps.close_app("Maya AI") == (
        "ERROR: Maya AI is protected and cannot close itself."
    )


def test_close_active_window_refuses_maya_window(monkeypatch):
    closed = []
    maya = SimpleNamespace(title="Maya AI", close=lambda: closed.append(True))
    fake_gw = SimpleNamespace(getActiveWindow=lambda: maya)
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)

    result = apps.close_active_window()

    assert result == (
        "ERROR: The active window 'Maya AI' is protected and cannot be closed."
    )
    assert closed == []


def test_close_active_window_refuses_runtime_owned_window(monkeypatch):
    host = SimpleNamespace(
        title="RELIABILITY_AUDIT.md - Visual Studio Code",
        _hWnd=777,
        close=lambda: pytest.fail("runtime-owned window must not be closed"),
    )
    fake_gw = SimpleNamespace(getActiveWindow=lambda: host)
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(apps, "_window_is_protected_runtime", lambda window: True)

    result = apps.close_active_window()

    assert result == (
        "ERROR: The active window "
        "'RELIABILITY_AUDIT.md - Visual Studio Code' is protected and cannot be closed."
    )


def test_manage_window_close_reuses_runtime_window_protection(monkeypatch):
    protected = SimpleNamespace(
        title="Maya AI",
        _hWnd=501,
        close=lambda: pytest.fail("protected runtime window must not be closed"),
    )
    fake_gw = SimpleNamespace(
        getActiveWindow=lambda: protected,
        getAllWindows=lambda: [protected],
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(apps, "_window_is_protected_runtime", lambda window: True)

    result = shortcuts.manage_window("close")

    assert result == "ERROR: Window 'Maya AI' is protected and cannot be closed."


def test_manage_window_close_reports_partial_until_window_is_gone(monkeypatch):
    close_calls = []
    target = SimpleNamespace(
        title="Unsaved - Notepad",
        _hWnd=777,
        close=lambda: close_calls.append(True),
    )
    fake_gw = SimpleNamespace(
        getActiveWindow=lambda: target,
        getAllWindows=lambda: [target],
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", fake_gw)
    monkeypatch.setattr(apps, "_window_is_protected_runtime", lambda window: False)
    monkeypatch.setattr(
        apps,
        "_wait_for_matching_windows",
        lambda _gw, predicate: [target.title] if predicate(target) else [],
    )

    result = shortcuts.manage_window("close")

    assert close_calls == [True]
    assert result == (
        "PARTIAL: Requested close for window 'Unsaved - Notepad', but it remains open."
    )


def test_close_app_skips_runtime_host_process(monkeypatch):
    runtime = SimpleNamespace(
        pid=9876,
        info={"pid": 9876, "name": "python.exe"},
        terminate=lambda: pytest.fail("runtime process must not be terminated"),
    )
    monkeypatch.setitem(__import__("sys").modules, "pygetwindow", None)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [runtime])
    monkeypatch.setattr(apps, "_is_system_process", lambda proc: False)

    result = apps.close_app("python")

    assert result.startswith("ERROR:")
