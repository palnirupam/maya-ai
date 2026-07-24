import httpx
from unittest.mock import Mock, patch

from backend.tools.desktop.advanced.whatsapp_manager import WhatsAppManager


def test_send_message_reuses_request_id_across_transport_retry():
    manager = WhatsAppManager()
    success = Mock(status_code=200)
    success.json.return_value = {"success": True}

    with patch.object(manager, "start"), \
         patch.object(manager, "wait_for_connected", return_value=True), \
         patch("backend.tools.desktop.advanced.whatsapp_manager.time.sleep"), \
         patch(
             "backend.tools.desktop.advanced.whatsapp_manager.httpx.post",
             side_effect=[httpx.ReadTimeout("response lost"), success],
         ) as post:
        assert manager.send_message("9876543210", "hello") is True

    assert post.call_count == 2
    first_payload = post.call_args_list[0].kwargs["json"]
    second_payload = post.call_args_list[1].kwargs["json"]
    assert first_payload["requestId"]
    assert first_payload == second_payload


def test_send_message_receipt_reports_the_observed_message_id_and_status():
    manager = WhatsAppManager()
    success = Mock(status_code=200)
    success.json.return_value = {"success": True, "messageId": "msg-1", "status": "sent"}

    with patch.object(manager, "start", return_value=True), patch.object(
        manager, "wait_for_connected", return_value=True
    ), patch("backend.tools.desktop.advanced.whatsapp_manager.httpx.post", return_value=success):
        receipt = manager.send_message_receipt("9876543210", "hello")

    assert receipt == {
        "success": True,
        "message_id": "msg-1",
        "status": "sent",
        "deduplicated": False,
        "error": None,
    }


def test_send_file_reuses_request_id_across_transport_retry(tmp_path):
    manager = WhatsAppManager()
    attachment = tmp_path / "report.pdf"
    attachment.write_text("report", encoding="utf-8")
    success = Mock(status_code=200)
    success.json.return_value = {"success": True, "messageId": "msg-1"}

    with patch.object(manager, "start"), \
         patch.object(manager, "wait_for_connected", return_value=True), \
         patch("backend.tools.desktop.advanced.whatsapp_manager.time.sleep"), \
         patch(
             "backend.tools.desktop.advanced.whatsapp_manager.httpx.post",
             side_effect=[httpx.ReadTimeout("response lost"), success],
         ) as post:
        result = manager.send_file("9876543210", str(attachment))

    assert result["success"] is True
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"] == post.call_args_list[1].kwargs["json"]


def test_invalid_phone_and_message_fail_before_start_or_transport():
    manager = WhatsAppManager()
    with patch.object(manager, "start") as start, patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.post"
    ) as post:
        assert manager.send_message("12345", "hello") is False
        assert manager.send_message("9876543210", "") is False

    start.assert_not_called()
    post.assert_not_called()


def test_deterministic_send_rejection_is_not_retried():
    manager = WhatsAppManager()
    rejected = Mock(status_code=400)
    rejected.json.return_value = {"error": "Number is not registered on WhatsApp"}
    with patch.object(manager, "start"), patch.object(
        manager, "wait_for_connected", return_value=True
    ), patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.post",
        return_value=rejected,
    ) as post:
        assert manager.send_message("9876543210", "hello") is False

    post.assert_called_once()


def test_revoke_receipt_rejects_a_success_like_zero_count():
    manager = WhatsAppManager()
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "revoked": 0}

    with patch.object(manager, "start", return_value=True), patch.object(
        manager, "wait_for_connected", return_value=True
    ), patch("backend.tools.desktop.advanced.whatsapp_manager.httpx.post", return_value=response):
        receipt = manager.revoke_messages_receipt("9876543210", 1)

    assert receipt["success"] is False
    assert receipt["revoked"] == 0


def test_send_file_rejects_missing_or_sensitive_path_before_start(tmp_path):
    manager = WhatsAppManager()
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=secret", encoding="utf-8")
    with patch.object(manager, "start") as start:
        missing = manager.send_file("9876543210", str(tmp_path / "missing.pdf"))
        protected = manager.send_file("9876543210", str(secret))

    assert missing["error"] == "Attachment file does not exist"
    assert protected["error"] == "Attachment path is protected"
    start.assert_not_called()


def test_send_file_deterministic_rejection_preserves_exact_error(tmp_path):
    manager = WhatsAppManager()
    attachment = tmp_path / "report.pdf"
    attachment.write_text("report", encoding="utf-8")
    rejected = Mock(status_code=403)
    rejected.json.return_value = {"error": "Attachment path is protected"}
    with patch.object(manager, "start"), patch.object(
        manager, "wait_for_connected", return_value=True
    ), patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.post",
        return_value=rejected,
    ) as post:
        result = manager.send_file("9876543210", str(attachment))

    assert result["error"] == "Attachment path is protected"
    post.assert_called_once()


def test_register_known_sender_posts_to_node_service():
    manager = WhatsAppManager()

    response = Mock()
    response.status_code = 200
    response.json.return_value = {"success": True}

    with patch("backend.tools.desktop.advanced.whatsapp_manager.httpx.post", return_value=response) as post:
        assert manager.register_known_sender("919876543210") is True

    post.assert_called_once_with(
        "http://127.0.0.1:9001/register-known",
        json={"number": "919876543210"},
        timeout=5.0,
        headers=manager._get_headers(),
    )


def test_register_known_sender_returns_false_on_error():
    manager = WhatsAppManager()

    with patch("backend.tools.desktop.advanced.whatsapp_manager.httpx.post", side_effect=RuntimeError("down")):
        assert manager.register_known_sender("919876543210") is False


def test_sender_authorization_rejects_invalid_number_before_transport():
    manager = WhatsAppManager()

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.post"
    ) as post:
        assert manager.register_known_sender("12345") is False
        assert manager.block_sender("12345") is False

    post.assert_not_called()


def test_block_sender_requires_success_response():
    manager = WhatsAppManager()
    response = Mock(status_code=200)
    response.json.return_value = {"success": False}

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.post",
        return_value=response,
    ):
        assert manager.block_sender("919876543210") is False


def test_start_reuses_authenticated_existing_service_without_spawning():
    manager = WhatsAppManager()
    response = Mock(status_code=200)

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.get",
        return_value=response,
    ), patch(
        "backend.tools.desktop.advanced.whatsapp_manager.subprocess.Popen"
    ) as popen, patch.object(manager, "_port_9001_is_listening") as listening:
        assert manager.start() is True

    popen.assert_not_called()
    listening.assert_not_called()
    assert manager._startup_error is None


def test_start_fails_closed_when_existing_service_rejects_credentials():
    manager = WhatsAppManager()
    response = Mock(status_code=401)

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.get",
        return_value=response,
    ), patch(
        "backend.tools.desktop.advanced.whatsapp_manager.subprocess.Popen"
    ) as popen, patch.object(manager, "_port_9001_is_listening") as listening:
        assert manager.start() is False

    popen.assert_not_called()
    listening.assert_not_called()
    assert "rejected Maya credentials" in manager._startup_error


def test_start_never_kills_unknown_tcp_port_owner():
    manager = WhatsAppManager()

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.get",
        side_effect=httpx.ConnectError("not HTTP"),
    ), patch.object(
        manager, "_port_9001_is_listening", return_value=True
    ), patch(
        "backend.tools.desktop.advanced.whatsapp_manager.subprocess.Popen"
    ) as popen, patch(
        "backend.tools.desktop.advanced.whatsapp_manager.subprocess.run"
    ) as run:
        assert manager.start() is False

    popen.assert_not_called()
    run.assert_not_called()
    assert "another local service" in manager._startup_error


def test_start_closes_stale_process_log_before_reusing_existing_service():
    manager = WhatsAppManager()
    stale_process = Mock()
    stale_process.poll.return_value = 1
    log_file = Mock()
    manager.process = stale_process
    manager.log_file = log_file

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.get",
        return_value=Mock(status_code=200),
    ), patch(
        "backend.tools.desktop.advanced.whatsapp_manager.subprocess.Popen"
    ) as popen:
        assert manager.start() is True

    log_file.close.assert_called_once_with()
    popen.assert_not_called()
    assert manager.process is None
    assert manager.log_file is None


def test_stop_closes_log_and_retains_live_process_when_termination_fails():
    manager = WhatsAppManager()
    process = Mock()
    process.terminate.side_effect = RuntimeError("denied")
    process.poll.return_value = None
    log_file = Mock()
    manager.process = process
    manager.log_file = log_file

    manager.stop()

    log_file.close.assert_called_once_with()
    assert manager.process is process
    assert manager.log_file is None


def test_stop_closes_log_when_process_poll_fails():
    manager = WhatsAppManager()
    process = Mock()
    process.terminate.side_effect = RuntimeError("denied")
    process.poll.side_effect = RuntimeError("poll denied")
    log_file = Mock()
    manager.process = process
    manager.log_file = log_file

    manager.stop()

    log_file.close.assert_called_once_with()
    assert manager.process is process
    assert manager.log_file is None


def test_send_message_fails_fast_when_service_startup_failed():
    manager = WhatsAppManager()
    manager._startup_error = "Port conflict"

    with patch.object(manager, "start", return_value=False), patch.object(
        manager, "wait_for_connected"
    ) as wait, patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.post"
    ) as post:
        assert manager.send_message("9876543210", "hello") is False

    wait.assert_not_called()
    post.assert_not_called()


def test_get_status_surfaces_known_startup_error_without_polling():
    manager = WhatsAppManager()
    manager._startup_error = "Port conflict"

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.get"
    ) as get:
        status = manager.get_status()
        assert status["available"] is False
        assert status["error"] == "Port conflict"

    get.assert_not_called()



def test_reply_to_chat_logs_no_chat_id_or_response_body():
    manager = WhatsAppManager()
    response = Mock(status_code=500, text="recipient=919876543210 body=secret")
    response.json.return_value = {"success": False}

    with patch(
        "backend.tools.desktop.advanced.whatsapp_manager.httpx.post",
        return_value=response,
    ), patch(
        "backend.tools.desktop.advanced.whatsapp_manager.logger.warning"
    ) as warning:
        assert manager.reply_to_chat("919876543210@c.us", "secret") is False

    rendered = " ".join(str(value) for value in warning.call_args.args)
    assert "919876543210" not in rendered
    assert "secret" not in rendered
    assert "500" in rendered
