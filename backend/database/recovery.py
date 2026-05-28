import hashlib
import secrets

# A small subset of BIP39 wordlist for demonstration
WORDLIST = [
    "abandon", "ability", "able", "about", "above", "absent", "absorb", "abstract",
    "absurd", "abuse", "access", "accident", "account", "accuse", "achieve", "acid",
    "acoustic", "acquire", "across", "act", "action", "actor", "actress", "actual",
    "adapt", "add", "addict", "address", "adjust", "admit", "adult", "advance",
    "advice", "aerobic", "affair", "afford", "afraid", "again", "age", "agent",
    "agree", "ahead", "aim", "air", "airport", "aisle", "alarm", "album", "alcohol",
    "alert", "alien", "all", "alley", "allow", "almost", "alone", "alpha", "already",
    "also", "alter", "always", "amateur", "amazing", "among", "amount", "amused"
] # 64 words for 6 bits each

class RecoveryManager:
    @staticmethod
    def generate_seed_phrase() -> str:
        """Generates a 12-word seed phrase."""
        # For a real implementation, 'mnemonic' package is recommended.
        # This is a functional local implementation mapping 72 bits to 12 words (6 bits each).
        random_bytes = secrets.token_bytes(9) # 72 bits
        bits = bin(int.from_bytes(random_bytes, byteorder='big'))[2:].zfill(72)
        
        words = []
        for i in range(0, 72, 6):
            chunk = bits[i:i+6]
            index = int(chunk, 2)
            words.append(WORDLIST[index])
            
        return " ".join(words)
        
    @staticmethod
    def seed_to_key(seed_phrase: str) -> bytes:
        """Derives a backup encryption key from the seed phrase."""
        # Use PBKDF2 on the seed phrase to generate the 32-byte recovery key
        salt = b"maya_ai_recovery_salt"
        return hashlib.pbkdf2_hmac(
            'sha256',
            seed_phrase.encode('utf-8'),
            salt,
            100000,
            dklen=32
        )

recovery_manager = RecoveryManager()
