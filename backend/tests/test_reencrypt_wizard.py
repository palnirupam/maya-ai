import unittest
import shutil
from pathlib import Path

DB_PATH = Path("data/memory.db")
BACKUP_PATH = Path("data/memory.db.backup")

def backup_database():
    """Helper to backup database - used in test."""
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUP_PATH)
        return True
    return False

class TestReencryptWizard(unittest.TestCase):
    def setUp(self):
        if not DB_PATH.parent.exists():
            DB_PATH.parent.mkdir(parents=True)
        # Use the real DB if it exists, otherwise create dummy
        if not DB_PATH.exists():
            DB_PATH.write_bytes(b"dummy database content")
            self.created_dummy = True
        else:
            self.created_dummy = False

    def test_backup_database(self):
        if BACKUP_PATH.exists():
            BACKUP_PATH.unlink()

        result = backup_database()

        self.assertTrue(result)
        self.assertTrue(BACKUP_PATH.exists())
        self.assertEqual(BACKUP_PATH.read_bytes(), DB_PATH.read_bytes())

    def tearDown(self):
        if hasattr(self, 'created_dummy') and self.created_dummy:
            if DB_PATH.exists():
                DB_PATH.unlink()
        if BACKUP_PATH.exists():
            BACKUP_PATH.unlink()

if __name__ == "__main__":
    unittest.main()
