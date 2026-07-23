r"""Regression tests for small tool-layer fixes surfaced by the audit."""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open

from backend.tools.unified.core.policy import is_safe_path
from backend.tools.desktop.advanced import youtube_player


class TestIsSafePathGuards(unittest.TestCase):
    r"""Audit finding: is_safe_path used prefix match without a separator, so
    legitimate sibling paths like C:\Windows-Backup or C:\maya-ai-2 were
    wrongly rejected as protected paths."""

    def test_exact_windows_dir_blocked(self):
        self.assertFalse(is_safe_path(r"C:\Windows"))
        self.assertFalse(is_safe_path(r"C:\Windows\\System32"))

    def test_sibling_of_windows_allowed(self):
        self.assertTrue(is_safe_path(r"C:\Windows-Backup\old.zip"))
        self.assertTrue(is_safe_path(r"C:\Recovery-Notes"))

    def test_sibling_of_maya_dir_allowed(self):
        self.assertTrue(is_safe_path(r"C:\maya-ai-2\project"))


class TestBackgroundPlayerStartup(unittest.TestCase):
    def _youtube_info(self):
        return {
            "entries": [{
                "title": "Test Song",
                "formats": [{
                    "acodec": "opus",
                    "vcodec": "none",
                    "abr": 128,
                    "url": "https://stream.example/audio",
                }],
            }]
        }

    def test_does_not_claim_success_when_vlc_exits_immediately(self):
        ydl = MagicMock()
        ydl.__enter__.return_value.extract_info.return_value = self._youtube_info()
        proc = SimpleNamespace(pid=1234, poll=lambda: 1)

        with patch.object(youtube_player.os.path, "exists", return_value=True), \
             patch.object(youtube_player, "_kill_existing_player"), \
             patch.object(youtube_player, "_save_pid"), \
             patch.object(youtube_player.os, "remove"), \
             patch.object(youtube_player.time, "sleep"), \
             patch.object(youtube_player.subprocess, "Popen", return_value=proc), \
             patch("yt_dlp.YoutubeDL", return_value=ydl):
            result = youtube_player.play_youtube_background("test song")

        self.assertTrue(result.startswith("ERROR:"), result)
        self.assertNotIn("Now playing", result)

    def test_reports_success_only_when_vlc_stays_alive(self):
        ydl = MagicMock()
        ydl.__enter__.return_value.extract_info.return_value = self._youtube_info()
        proc = SimpleNamespace(pid=1234, poll=lambda: None)

        with patch.object(youtube_player.os.path, "exists", return_value=True), \
             patch.object(youtube_player, "_kill_existing_player"), \
             patch.object(youtube_player, "_save_pid"), \
             patch.object(youtube_player.time, "sleep"), \
             patch.object(youtube_player.subprocess, "Popen", return_value=proc), \
             patch("yt_dlp.YoutubeDL", return_value=ydl):
            result = youtube_player.play_youtube_background("test song")

        self.assertTrue(result.startswith("SUCCESS:"), result)


class TestBackgroundPlayerStop(unittest.TestCase):
    r"""Audit finding (R08/S01): stop must only ever terminate the exact VLC
    process Maya started via its saved PID. It must never image-wide
    `taskkill /IM vlc.exe`, which would kill a user's own unrelated VLC
    instance (a protected-target violation) while falsely claiming success."""

    def test_stop_with_no_pid_file_never_image_kills_and_is_truthful(self):
        with patch.object(youtube_player.os.path, "exists", return_value=False), \
             patch.object(youtube_player.subprocess, "run") as run:
            result = youtube_player.stop_youtube_background()

        run.assert_not_called()
        self.assertEqual(result, "No background audio is currently playing.")

    def test_stop_never_uses_image_wide_taskkill(self):
        # Even when a PID file points at a live non-VLC (recycled) PID, stop
        # must not kill it and must not fall back to image-wide taskkill.
        proc = SimpleNamespace(name=lambda: "chrome.exe")
        with patch.object(youtube_player.os.path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="4321")), \
             patch.object(youtube_player.psutil, "pid_exists", return_value=True), \
             patch.object(youtube_player.psutil, "Process", return_value=proc), \
             patch.object(youtube_player.os, "remove"), \
             patch.object(youtube_player.subprocess, "run") as run:
            result = youtube_player.stop_youtube_background()

        # No taskkill of any kind for a recycled/non-VLC PID.
        for call in run.call_args_list:
            args = call.args[0] if call.args else []
            self.assertNotIn("/IM", args)
        self.assertIn("No background audio", result)

    def test_taskkill_fallback_targets_exact_pid_not_image(self):
        completed = SimpleNamespace(returncode=0, stderr="", stdout="")
        with patch.object(youtube_player.os, "remove"), \
             patch.object(youtube_player.subprocess, "run", return_value=completed) as run:
            result = youtube_player._taskkill_vlc(4321)

        args = run.call_args.args[0]
        self.assertIn("/PID", args)
        self.assertIn("4321", args)
        self.assertNotIn("/IM", args)
        self.assertTrue(result.startswith("SUCCESS:"), result)


if __name__ == "__main__":
    unittest.main()
