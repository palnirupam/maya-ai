import unittest
from unittest.mock import patch
from pathlib import Path
import hashlib
from backend.skills.loader import verify_and_load_plugin

class TestPluginSecurity(unittest.TestCase):
    def setUp(self):
        self.safe_code = "def my_plugin():\n    return 'hello'"
        self.malicious_code = "import subprocess\ndef my_plugin():\n    subprocess.run('echo hacked', shell=True)"
        
        self.safe_plugin_path = Path("safe_plugin.py")
        self.malicious_plugin_path = Path("malicious_plugin.py")
        
        self.safe_plugin_path.write_text(self.safe_code)
        self.malicious_plugin_path.write_text(self.malicious_code)
        
        self.safe_hash = hashlib.sha256(self.safe_code.encode("utf-8")).hexdigest()
        self.malicious_hash = hashlib.sha256(self.malicious_code.encode("utf-8")).hexdigest()
        
    @patch('backend.skills.loader.load_registry')
    def test_safe_plugin_loads(self, mock_registry):
        mock_registry.return_value = {"safe_plugin": self.safe_hash}
        self.assertTrue(verify_and_load_plugin(self.safe_plugin_path))
        
    @patch('backend.skills.loader.load_registry')
    def test_malicious_plugin_blocked_by_ast(self, mock_registry):
        mock_registry.return_value = {"malicious_plugin": self.malicious_hash}
        # It's in the registry and hash matches, but AST should block it!
        self.assertFalse(verify_and_load_plugin(self.malicious_plugin_path))
        
    @patch('backend.skills.loader.load_registry')
    def test_plugin_blocked_by_hash_mismatch(self, mock_registry):
        mock_registry.return_value = {"safe_plugin": "wrong_hash_12345"}
        self.assertFalse(verify_and_load_plugin(self.safe_plugin_path))
        
    def tearDown(self):
        if self.safe_plugin_path.exists():
            self.safe_plugin_path.unlink()
        if self.malicious_plugin_path.exists():
            self.malicious_plugin_path.unlink()

if __name__ == "__main__":
    unittest.main()
