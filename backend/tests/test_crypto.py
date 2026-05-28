import unittest
from backend.database.crypto import crypto_manager

class TestCrypto(unittest.TestCase):
    def test_encryption_decryption(self):
        original_text = "secret_password_123"
        encrypted = crypto_manager.encrypt(original_text)
        
        self.assertNotEqual(original_text, encrypted)
        self.assertTrue(len(encrypted) > 0)
        
        decrypted = crypto_manager.decrypt(encrypted)
        self.assertEqual(original_text, decrypted)

if __name__ == "__main__":
    unittest.main()
