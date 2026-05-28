import unittest
from backend.database.recovery import recovery_manager

class TestRecoveryManager(unittest.TestCase):
    def test_seed_phrase_generation_and_key(self):
        phrase = recovery_manager.generate_seed_phrase()
        words = phrase.split()
        
        self.assertEqual(len(words), 12)
        
        # Test key derivation
        key = recovery_manager.seed_to_key(phrase)
        self.assertEqual(len(key), 32)
        
        # Consistent key for same phrase
        key2 = recovery_manager.seed_to_key(phrase)
        self.assertEqual(key, key2)

if __name__ == "__main__":
    unittest.main()
