import unittest
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory


def backup_database(db_path, backup_path):
    """Helper to backup database - used in test."""
    if db_path.exists():
        shutil.copy2(db_path, backup_path)
        return True
    return False

class TestReencryptWizard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.db"
        self.backup_path = Path(self.temp_dir.name) / "memory.db.backup"
        self.db_path.write_bytes(b"dummy database content")

    def test_backup_database(self):
        result = backup_database(self.db_path, self.backup_path)

        self.assertTrue(result)
        self.assertTrue(self.backup_path.exists())
        self.assertEqual(self.backup_path.read_bytes(), self.db_path.read_bytes())

    def tearDown(self):
        self.temp_dir.cleanup()

if __name__ == "__main__":
    unittest.main()
