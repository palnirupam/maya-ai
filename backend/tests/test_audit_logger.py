import os
import unittest
from pathlib import Path
from backend.utils.audit_logger import audit_logger, LOG_FILE

class TestAuditLogger(unittest.TestCase):
    def test_log_creation_and_append(self):
        # Write a test event
        test_msg = "TEST_SECURITY_EVENT: Unauthorized access attempt"
        audit_logger.warning(test_msg)
        
        # Verify file exists
        self.assertTrue(LOG_FILE.exists())
        
        # Verify message was appended
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn(test_msg, content)

if __name__ == "__main__":
    unittest.main()
