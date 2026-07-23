import asyncio
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.api.security import (
    is_loopback_host,
    is_trusted_origin,
    parse_client_event,
)
from backend.brain.agents.agent_team import _canonical_action, _tool_call_requires_approval
from backend.brain.reasoning.tool_planner import ToolPlanner
from backend.database.connection import engine
from backend.security.audit_logger import AuditLogger
from backend.security.risk_classifier import RiskClassifier
from backend.tools.unified.core.policy import _MAYA_DIR
from backend.tools.unified.handlers.file_ops import handle_file
from backend.tools.unified.handlers.system_ops import handle_pc


def test_action_approval_gate_normalizes_case_separators_and_aliases():
    dangerous_calls = [
        ("perform_shortcut", {"action": "Restart"}),
        ("perform_shortcut", {"action": " SUSPEND "}),
        ("pc", {"action": "Process-Kill"}),
        ("file", {"action": "DELETE BY NAME"}),
    ]

    for tool_name, payload in dangerous_calls:
        assert _tool_call_requires_approval(tool_name, payload)

    assert _canonical_action(" SUSPEND ") == "sleep"
    assert not _tool_call_requires_approval("perform_shortcut", {"action": "mute"})


def test_risk_classifier_matches_the_approval_gate_action_normalization():
    classifier = RiskClassifier()

    assert classifier.classify("perform_shortcut", {"action": "Restart"}) == "HIGH"
    assert classifier.classify("perform_shortcut", {"action": "suspend"}) == "HIGH"
    assert classifier.classify("file", {"action": "DELETE-BY-NAME"}) == "CRITICAL"


def test_audit_logger_redacts_nested_credentials_and_message_content(tmp_path):
    logger = AuditLogger(log_dir=str(tmp_path))

    logger.log_approval(
        request_id="req-1",
        tool_name="whatsapp_send_message",
        payload={
            "message": "private hello",
            "password": "wifi-password",
            "nested": {"api_key": "secret-key"},
        },
        risk_level="HIGH",
        approved=True,
        approved_by="test",
        latency_ms=10,
    )

    entry = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    payload = entry["payload"]
    assert payload["password"] == "<redacted>"
    assert payload["nested"]["api_key"] == "<redacted>"
    assert "private hello" not in payload["message"]
    assert payload["message"].startswith("<redacted sha256=")


def test_audit_logger_redacts_private_payloads_for_mcp_tools(tmp_path):
    logger = AuditLogger(log_dir=str(tmp_path))

    logger.log_approval(
        request_id="req-mcp-1",
        tool_name="demo__send_record",
        payload={"message": "private account details", "query": "public term"},
        risk_level="HIGH",
        approved=True,
        approved_by="test",
        latency_ms=10,
    )

    entry = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    assert "private account details" not in entry["payload"]["message"]
    assert entry["payload"]["message"].startswith("<redacted sha256=")
    assert entry["payload"]["query"] == "public term"


def test_risk_classifier_understands_unified_actions():
    classifier = RiskClassifier()

    assert classifier.classify("file", {"action": "delete"}) == "HIGH"
    assert classifier.classify("file", {"action": "delete_by_name"}) == "CRITICAL"
    assert classifier.classify("pc", {"action": "shutdown"}) == "HIGH"
    assert classifier.classify("pc", {"action": "wifi_connect"}) == "MEDIUM"
    assert classifier.classify("pc", {"action": "battery"}) == "LOW"
    assert classifier.classify("close_apps_except", {"excluded_apps": "vs code"}) == "HIGH"
    assert classifier.classify("configure_mcp_server", {"npm_package": "@demo/mcp"}) == "HIGH"
    assert classifier.classify("execute_python", {"code": "print('hello')"}) == "HIGH"
    assert classifier.classify("execute_powershell", {"command": "Get-Date"}) == "HIGH"
    assert classifier.classify("execute_powershell", {"command": "rm -rf C:/tmp"}) == "CRITICAL"


@pytest.mark.asyncio
async def test_danger_marker_has_high_minimum_risk():
    planner = ToolPlanner()
    fake_db = MagicMock()
    with patch("backend.brain.reasoning.tool_planner.SessionLocal", return_value=fake_db):
        request = planner.queue_tool("new_host_mutation", {}, risk_level="danger")

    assert request["risk_level"] == "HIGH"
    future_data = planner._memory_futures.pop(request["request_id"])
    future_data["future"].cancel()


@pytest.mark.asyncio
async def test_approval_queue_fails_closed_when_persistence_fails():
    planner = ToolPlanner()
    fake_db = MagicMock()
    fake_db.commit.side_effect = RuntimeError("database unavailable")

    with patch("backend.brain.reasoning.tool_planner.SessionLocal", return_value=fake_db):
        request = planner.queue_tool("execute_python", {"code": "print('hello')"})

    assert request["status"] == "error"
    assert request["request_id"] not in planner._memory_futures
    fake_db.rollback.assert_called_once_with()


@pytest.mark.asyncio
async def test_inactive_approval_lookup_fails_closed_on_database_error():
    planner = ToolPlanner()

    with patch(
        "backend.brain.reasoning.tool_planner.SessionLocal",
        side_effect=RuntimeError("database unavailable"),
    ):
        assert await planner.wait_for_approval(str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_stale_pending_approval_cannot_be_approved():
    planner = ToolPlanner()
    record = SimpleNamespace(
        tool_name="execute_python",
        payload={"code": "print('safe')"},
        risk_level="HIGH",
        status="pending",
        expires_at=None,
    )
    fake_db = MagicMock()
    fake_db.query.return_value.filter_by.return_value.first.return_value = record

    with (
        patch("backend.brain.reasoning.tool_planner.SessionLocal", return_value=fake_db),
        patch("backend.brain.reasoning.tool_planner.audit_logger.log_approval") as log_approval,
    ):
        result = planner.resolve_tool(str(uuid.uuid4()), approved=True)

    assert result["status"] == "expired"
    assert record.status == "expired"
    fake_db.commit.assert_called_once_with()
    assert log_approval.call_args.kwargs["approved"] is False


@pytest.mark.asyncio
async def test_terminal_approval_cannot_be_resolved_twice():
    planner = ToolPlanner()
    request_id = str(uuid.uuid4())
    future = asyncio.get_running_loop().create_future()
    planner._memory_futures[request_id] = {"future": future, "created_at_ts": 0.0}
    record = SimpleNamespace(
        tool_name="execute_python",
        payload={"code": "print('safe')"},
        risk_level="HIGH",
        status="approved",
        expires_at=None,
    )
    fake_db = MagicMock()
    fake_db.query.return_value.filter_by.return_value.first.return_value = record

    with patch("backend.brain.reasoning.tool_planner.SessionLocal", return_value=fake_db):
        result = planner.resolve_tool(request_id, approved=True)

    assert result["status"] == "approved"
    assert future.result() is False
    fake_db.commit.assert_not_called()
    planner._memory_futures.pop(request_id)


def test_test_database_is_not_the_production_database():
    configured = Path(engine.url.database).resolve()
    production = (Path(__file__).resolve().parents[2] / "data" / "memory.db").resolve()

    assert os.environ.get("MAYA_TESTING") == "1"
    assert configured != production
    assert configured.parent == Path(os.environ["MAYA_DATA_DIR"]).resolve()


def test_local_boundary_and_websocket_event_schema():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("::1")
    assert not is_loopback_host("192.0.2.10")
    assert is_trusted_origin("http://localhost:1420")
    assert not is_trusted_origin("https://evil.example")

    event_type, payload = parse_client_event(
        json.dumps({"type": "text_message", "data": {"text": "hello"}})
    )
    assert event_type == "text_message"
    assert payload["text"] == "hello"

    with pytest.raises(ValueError):
        parse_client_event(json.dumps({"type": "unknown", "data": {}}))
    with pytest.raises(ValueError):
        parse_client_event(
            json.dumps(
                {
                    "type": "tool_approval_response",
                    "data": {"request_id": "not-a-uuid", "approved": True},
                }
            )
        )


def test_unified_screenshot_uses_sensitive_screen_guard():
    with patch(
        "backend.tools.desktop.advanced.vision_tools.take_verified_screenshot",
        return_value="BLOCKED: Sensitive app on screen. Cannot capture screenshot.",
    ) as screenshot:
        result = handle_pc("screenshot")

    screenshot.assert_called_once_with()
    assert result.startswith("BLOCKED:")


def test_power_command_reports_subprocess_failure():
    failed = SimpleNamespace(returncode=1, stdout="", stderr="Access denied")
    with patch(
        "backend.tools.unified.handlers.system_ops.subprocess.run",
        return_value=failed,
    ) as run:
        result = handle_pc("shutdown")

    run.assert_called_once_with(
        ["shutdown", "/s", "/t", "5"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result == "ERR: Access denied"


def test_power_command_only_reports_success_on_zero_exit():
    succeeded = SimpleNamespace(returncode=0, stdout="", stderr="")
    with patch(
        "backend.tools.unified.handlers.system_ops.subprocess.run",
        return_value=succeeded,
    ):
        assert handle_pc("restart") == "OK: restarting in 5s"
        assert handle_pc("sleep") == "OK: sleep"


def test_unified_process_kill_refuses_protected_runtime_target():
    protected = MagicMock()
    protected.pid = 4242
    protected.info = {"pid": 4242, "name": "python.exe"}

    with (
        patch("backend.tools.unified.handlers.system_ops.psutil.Process", return_value=protected),
        patch(
            "backend.tools.unified.handlers.system_ops._process_kill_is_protected",
            return_value=True,
        ),
    ):
        result = handle_pc("process_kill", val=4242)

    assert result.startswith("ERR: Refused to kill")
    protected.kill.assert_not_called()


def test_unified_process_kill_waits_for_exit_before_reporting_success():
    target = MagicMock()
    target.pid = 4243
    target.info = {"pid": 4243, "name": "notepad.exe"}

    with (
        patch("backend.tools.unified.handlers.system_ops.psutil.Process", return_value=target),
        patch(
            "backend.tools.unified.handlers.system_ops._process_kill_is_protected",
            return_value=False,
        ),
    ):
        result = handle_pc("process_kill", val=4243)

    target.kill.assert_called_once_with()
    target.wait.assert_called_once_with(timeout=3)
    assert result == "OK: killed notepad.exe"


def test_mkdir_and_list_refuse_project_directory():
    protected_child = str(Path(_MAYA_DIR) / "should-not-be-created-by-test")

    assert handle_file("mkdir", path=protected_child) == "ERR: protected path"
    assert handle_file("ls", path=_MAYA_DIR) == "ERR: protected path"
    assert handle_file("organize", path=_MAYA_DIR) == "ERR: protected path"
    assert not Path(protected_child).exists()
