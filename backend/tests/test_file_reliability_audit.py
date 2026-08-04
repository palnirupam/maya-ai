import errno
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from backend.tools.unified.core import path as path_utils
from backend.tools.unified.core.policy import is_sensitive_path
from backend.tools.unified.handlers.file_ops import handle_file


def test_unified_file_actions_round_trip_on_real_temp_data(tmp_path):
    root = tmp_path / "audit"
    assert handle_file("mkdir", path=str(root)).startswith("OK:")

    source = root / "source.txt"
    assert handle_file("write", src=str(source), dst="audit payload").startswith("OK:")
    assert handle_file("read", src=str(source)) == "audit payload"
    assert "source.txt" in handle_file("ls", path=str(root))

    copied = root / "copied.txt"
    assert handle_file("copy", src=str(source), dst=str(copied)).startswith("OK:")
    moved = root / "moved.txt"
    assert handle_file("move", src=str(copied), dst=str(moved)).startswith("OK:")
    assert not copied.exists() and moved.exists()

    assert handle_file("rename", src=str(moved), dst="renamed.txt").startswith("OK:")
    renamed = root / "renamed.txt"
    assert renamed.exists()
    assert handle_file("delete", src=str(renamed)).startswith("OK:")
    assert not renamed.exists()


@pytest.mark.parametrize("filename", ["Open.html", "report.pdf", "photo.png"])
def test_open_launches_browser_supported_file_by_exact_path(tmp_path, monkeypatch, filename):
    target = tmp_path / filename
    target.write_text("browser payload", encoding="utf-8")
    opened = []
    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.webbrowser.open",
        lambda url, new=0: opened.append((url, new)) or True,
    )

    result = handle_file("open", src=str(target))

    assert result == f"OK: opened {target} in the default browser"
    assert opened == [(target.resolve().as_uri(), 2)]


def test_open_finds_a_named_file_before_launching(tmp_path, monkeypatch):
    target = tmp_path / "Open.html"
    target.write_text("<h1>Maya</h1>", encoding="utf-8")
    monkeypatch.setattr(path_utils, "get_known_folders", lambda: [str(tmp_path)])
    monkeypatch.setattr(path_utils.string, "ascii_uppercase", "")
    opened = []
    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.webbrowser.open",
        lambda url, new=0: opened.append(url) or True,
    )

    result = handle_file("open", name="Open.html")

    assert result == f"OK: opened {target} in the default browser"
    assert opened == [target.resolve().as_uri()]


def test_open_rejects_executable_and_does_not_launch(tmp_path, monkeypatch):
    target = tmp_path / "unsafe.exe"
    target.write_bytes(b"MZ")
    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.webbrowser.open",
        lambda *args, **kwargs: pytest.fail("unsupported files must not be launched"),
    )

    assert handle_file("open", src=str(target)) == "ERR: .exe is not supported for browser opening"


def test_write_dedupes_instead_of_silently_overwriting(tmp_path):
    target = tmp_path / "report.txt"
    target.write_text("original", encoding="utf-8")

    result = handle_file("write", src=str(target), dst="replacement")

    deduped = tmp_path / "report (1).txt"
    assert result == f"OK: {deduped}"
    assert target.read_text(encoding="utf-8") == "original"
    assert deduped.read_text(encoding="utf-8") == "replacement"


def test_rename_cannot_escape_the_source_directory(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")

    result = handle_file("rename", src=str(source), dst="../escaped.txt")

    assert result == "ERR: rename destination must be a file name in the same directory"
    assert source.exists()
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_project_path_traversal_is_protected(tmp_path):
    project_target = Path(__file__).resolve().parents[2] / "audit-escape.txt"
    traversed = tmp_path / os.path.relpath(project_target, tmp_path)

    assert handle_file("write", src=str(traversed), dst="blocked") == "ERR: protected path"
    assert not project_target.exists()


@pytest.mark.parametrize(
    "relative_path",
    [
        ".env",
        ".env.production",
        ".ssh/id_rsa",
        ".aws/credentials",
        ".docker/config.json",
        "credentials.json",
        "private-key.pem",
    ],
)
def test_sensitive_credential_paths_are_protected(tmp_path, relative_path):
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("API_KEY=do-not-expose", encoding="utf-8")

    assert is_sensitive_path(str(target))
    assert handle_file("read", src=str(target)) == "ERR: protected path"
    assert handle_file("copy", src=str(target), dst=str(tmp_path / "copy")) == "ERR: protected path"
    assert handle_file("delete", src=str(target)) == "ERR: protected path"
    assert target.exists()


def test_search_does_not_reveal_sensitive_paths(tmp_path, monkeypatch):
    secret = tmp_path / "credentials.json"
    secret.write_text('{"token":"do-not-expose"}', encoding="utf-8")
    visible = tmp_path / "credentials-guide.txt"
    visible.write_text("public documentation", encoding="utf-8")
    monkeypatch.setattr(path_utils, "get_known_folders", lambda: [str(tmp_path)])
    monkeypatch.setattr(path_utils.string, "ascii_uppercase", "")

    result = handle_file("search", name="credentials", n=5)

    assert str(secret) not in result
    assert str(visible) in result


def test_env_template_remains_available_for_normal_file_work(tmp_path):
    template = tmp_path / ".env.example"
    template.write_text("API_KEY=replace-me", encoding="utf-8")

    assert not is_sensitive_path(str(template))
    assert handle_file("read", src=str(template)) == "API_KEY=replace-me"


@pytest.mark.parametrize("action", ["search", "delete_by_name"])
def test_search_actions_reject_blank_names_without_scanning(monkeypatch, action):
    monkeypatch.setattr(
        path_utils,
        "get_known_folders",
        lambda: pytest.fail("blank queries must fail before filesystem discovery"),
    )

    assert handle_file(action, name="   ") == "ERR: name cannot be empty"


@pytest.mark.parametrize("n", [0, -1, 51, "many"])
def test_search_rejects_invalid_result_limits_without_scanning(monkeypatch, n):
    monkeypatch.setattr(
        path_utils,
        "get_known_folders",
        lambda: pytest.fail("invalid limits must fail before filesystem discovery"),
    )

    assert handle_file("search", name="report", n=n).startswith("ERR: n must ")


def test_search_deduplicates_overlapping_roots(tmp_path, monkeypatch):
    report = tmp_path / "report.txt"
    report.write_text("payload", encoding="utf-8")
    monkeypatch.setattr(path_utils, "get_known_folders", lambda: [str(tmp_path), str(tmp_path)])
    monkeypatch.setattr(path_utils.string, "ascii_uppercase", "")

    assert path_utils.find_items("report", 5) == [str(report)]


def test_copy_rejects_source_tree_containing_symlink(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("sensitive", encoding="utf-8")
    link = source / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = handle_file("copy", src=str(source), dst=str(tmp_path / "copy"))

    assert result == "ERR: copy source contains a symlink or reparse point"
    assert not (tmp_path / "copy").exists()


def test_copy_rejects_reparse_tree_without_platform_symlink_support(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    linked = source / "linked"
    linked.mkdir()
    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops._is_link_like",
        lambda path: os.path.normcase(str(path)) == os.path.normcase(str(linked)),
    )

    result = handle_file("copy", src=str(source), dst=str(tmp_path / "copy"))

    assert result == "ERR: copy source contains a symlink or reparse point"
    assert not (tmp_path / "copy").exists()


def test_delete_unlinks_symlink_without_deleting_target(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("keep", encoding="utf-8")
    link = tmp_path / "target-link.txt"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert handle_file("delete", src=str(link)) == f"OK: removed {link}"
    assert not link.exists()
    assert target.read_text(encoding="utf-8") == "keep"


def test_delete_reports_unverified_post_condition(tmp_path, monkeypatch):
    target = tmp_path / "stubborn.txt"
    target.write_text("keep", encoding="utf-8")
    monkeypatch.setattr("backend.tools.unified.handlers.file_ops._remove_path", lambda path: None)

    result = handle_file("delete", src=str(target))

    assert result == f"ERR: delete could not be verified for {target}"
    assert target.exists()


def test_copy_failure_removes_incomplete_staging_file(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    def interrupted_copy(src, dst):
        Path(dst).write_text("partial", encoding="utf-8")
        raise OSError("simulated interrupted copy")

    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.shutil.copy2", interrupted_copy
    )

    result = handle_file("copy", src=str(source), dst=str(destination))

    assert result == "ERR: simulated interrupted copy"
    assert source.read_text(encoding="utf-8") == "payload"
    assert not destination.exists()
    assert not list(tmp_path.glob(".destination.txt.maya-copy-*"))


def test_copy_rejects_destination_inside_source_tree(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.txt").write_text("payload", encoding="utf-8")
    destination = source / "nested-copy"

    result = handle_file("copy", src=str(source), dst=str(destination))

    assert result == "ERR: destination cannot be inside the source directory"
    assert not destination.exists()


def test_move_rejects_destination_inside_source_tree(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.txt").write_text("payload", encoding="utf-8")
    destination = source / "nested-move"

    result = handle_file("move", src=str(source), dst=str(destination))

    assert result == "ERR: destination cannot be inside the source directory"
    assert source.exists()
    assert not destination.exists()


def test_cross_drive_move_stages_then_removes_source(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    real_rename = os.rename
    calls = 0

    def cross_drive_first(src, dst):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.EXDEV, "simulated cross-device move")
        return real_rename(src, dst)

    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.os.rename", cross_drive_first
    )

    result = handle_file("move", src=str(source), dst=str(destination))

    assert result == f"OK: {destination}"
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "payload"
    assert not list(tmp_path.glob(".*.maya-*-*"))


def test_cross_drive_move_retire_failure_preserves_source_and_destination(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    real_rename = os.rename
    calls = 0

    def fail_source_retire(src, dst):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.EXDEV, "simulated cross-device move")
        if calls == 3:
            raise PermissionError("source is busy")
        return real_rename(src, dst)

    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.os.rename", fail_source_retire
    )

    result = handle_file("move", src=str(source), dst=str(destination))

    assert result.startswith("PARTIAL: destination created at ")
    assert f"source remains at {source}" in result
    assert source.read_text(encoding="utf-8") == "payload"
    assert destination.read_text(encoding="utf-8") == "payload"


def test_cross_drive_move_cleanup_failure_reports_recovery_path(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    real_rename = os.rename
    calls = 0

    def cross_drive_first(src, dst):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.EXDEV, "simulated cross-device move")
        return real_rename(src, dst)

    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops.os.rename", cross_drive_first
    )
    monkeypatch.setattr(
        "backend.tools.unified.handlers.file_ops._remove_path",
        lambda path: (_ for _ in ()).throw(PermissionError("cleanup denied")),
    )

    result = handle_file("move", src=str(source), dst=str(destination))

    assert result.startswith("PARTIAL: destination created at ")
    assert "source cleanup remains at" in result
    assert not source.exists()
    recovery = list(tmp_path.glob(".source.txt.maya-move-recovery-*"))
    assert len(recovery) == 1
    assert recovery[0].read_text(encoding="utf-8") == "payload"
    assert destination.read_text(encoding="utf-8") == "payload"


@pytest.mark.skipif(
    not (os.path.isdir("C:\\") and os.path.isdir("D:\\")),
    reason="real C: to D: cross-drive verification requires both drives",
)
def test_real_cross_drive_move_round_trip_preserves_content():
    c_parent = r"C:\tmp"
    source_root = None
    destination_root = None
    try:
        os.makedirs(c_parent, exist_ok=True)
        source_root = tempfile.mkdtemp(
            prefix="maya-r02-cross-drive-", dir=c_parent
        )
        destination_root = tempfile.mkdtemp(
            prefix="maya-r02-cross-drive-", dir="D:\\"
        )
    except OSError as exc:
        if source_root:
            shutil.rmtree(source_root, ignore_errors=True)
        if destination_root:
            shutil.rmtree(destination_root, ignore_errors=True)
        pytest.skip(
            "real cross-drive fixture roots are not writable in this "
            f"environment ({type(exc).__name__})"
        )

    try:
        source = os.path.join(source_root, "payload.bin")
        destination = os.path.join(destination_root, "payload.bin")
        payload = (b"maya-cross-drive-audit\x00" * 4096) + b"complete"
        with open(source, "wb") as file_handle:
            file_handle.write(payload)

        result = handle_file("move", src=source, dst=destination)

        assert result == f"OK: {destination}"
        assert not os.path.exists(source)
        with open(destination, "rb") as file_handle:
            assert file_handle.read() == payload
        assert not list(Path(destination_root).glob(".*.maya-*-*"))
    finally:
        shutil.rmtree(source_root, ignore_errors=True)
        shutil.rmtree(destination_root, ignore_errors=True)
