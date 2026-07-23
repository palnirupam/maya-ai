"""Unit tests for organize_folder (fast file organizer).

Uses real temp directories (pure filesystem, no GUI), so these run fast and
hermetically.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import tempfile
import shutil
import datetime
import unittest
from unittest.mock import patch

from backend.tools.desktop.advanced.file_system_tools import organize_folder


def _touch(path, when=None):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("x")
    if when is not None:
        os.utime(path, (when, when))


class TestOrganizeFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="maya_org_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _p(self, *parts):
        return os.path.join(self.tmp, *parts)

    def test_type_strategy_sorts_files(self):
        _touch(self._p("a.jpg"))
        _touch(self._p("b.pdf"))
        _touch(self._p("c.mp3"))
        _touch(self._p("d.zip"))
        _touch(self._p("e.xyz"))      # unknown ext -> Others
        _touch(self._p("s.lnk"))      # shortcut -> left in place
        os.makedirs(self._p("sub"))   # subfolder -> untouched

        res = organize_folder(self.tmp, strategy="type")

        self.assertTrue(os.path.isfile(self._p("Images", "a.jpg")))
        self.assertTrue(os.path.isfile(self._p("Documents", "b.pdf")))
        self.assertTrue(os.path.isfile(self._p("Audio", "c.mp3")))
        self.assertTrue(os.path.isfile(self._p("Archives", "d.zip")))
        self.assertTrue(os.path.isfile(self._p("Others", "e.xyz")))
        self.assertTrue(os.path.isfile(self._p("s.lnk")))     # shortcut untouched
        self.assertTrue(os.path.isdir(self._p("sub")))        # folder untouched
        self.assertIn("Organized", res)

    def test_dry_run_moves_nothing(self):
        _touch(self._p("a.jpg"))
        res = organize_folder(self.tmp, dry_run=True)
        self.assertTrue(os.path.isfile(self._p("a.jpg")))
        self.assertFalse(os.path.isdir(self._p("Images")))
        self.assertIn("Would organize", res)

    def test_collision_dedupe(self):
        os.makedirs(self._p("Images"))
        _touch(self._p("Images", "a.jpg"))   # pre-existing
        _touch(self._p("a.jpg"))             # loose duplicate name
        organize_folder(self.tmp, strategy="type")
        self.assertTrue(os.path.isfile(self._p("Images", "a.jpg")))
        self.assertTrue(os.path.isfile(self._p("Images", "a (1).jpg")))

    def test_date_strategy(self):
        when = datetime.datetime(2021, 5, 15, 12, 0, 0).timestamp()
        _touch(self._p("old.txt"), when=when)
        organize_folder(self.tmp, strategy="date")
        self.assertTrue(os.path.isfile(self._p("2021-05", "old.txt")))

    def test_nonexistent_folder(self):
        res = organize_folder(self._p("nope"))
        self.assertIn("ERROR", res)
        self.assertIn("does not exist", res)

    def test_unsafe_target_refused(self):
        res = organize_folder("C:\\Windows")
        self.assertIn("ERROR", res)
        self.assertIn("system/root", res)

    def test_already_tidy(self):
        os.makedirs(self._p("sub"))
        res = organize_folder(self.tmp)
        self.assertIn("Nothing to organize", res)

    def test_all_move_failures_report_error_not_success(self):
        _touch(self._p("a.jpg"))

        with patch(
            "backend.tools.desktop.advanced.file_system_tools.shutil.move",
            side_effect=OSError("disk unavailable"),
        ):
            res = organize_folder(self.tmp)

        self.assertTrue(res.startswith("ERROR:"), res)
        self.assertTrue(os.path.isfile(self._p("a.jpg")))

    def test_some_move_failures_report_partial_and_successful_counts(self):
        _touch(self._p("a.jpg"))
        _touch(self._p("b.pdf"))
        real_move = shutil.move

        def fail_images(src, dst):
            if src.endswith("a.jpg"):
                raise OSError("image destination unavailable")
            return real_move(src, dst)

        with patch(
            "backend.tools.desktop.advanced.file_system_tools.shutil.move",
            side_effect=fail_images,
        ):
            res = organize_folder(self.tmp)

        self.assertTrue(res.startswith("PARTIAL:"), res)
        self.assertIn("Organized 1 files", res)
        self.assertNotIn("Images: 1", res)
        self.assertTrue(os.path.isfile(self._p("a.jpg")))
        self.assertTrue(os.path.isfile(self._p("Documents", "b.pdf")))


if __name__ == "__main__":
    unittest.main()
