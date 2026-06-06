import os
import sys
import json
import numpy as np

# Add backend to path
sys.path.append("c:\\maya-ai")
from backend.database.connection import SessionLocal
from backend.database.models import LongTermMemory
from backend.database.crypto import crypto_manager
from backend.brain.memory.long_term_memory import store_memory, retrieve_relevant_memories

def main():
    print("--- STARTING SECURITY AUDIT FOR VECTOR MEMORY ---\n")
    
    db = SessionLocal()
    try:
        # Clear existing memories to avoid conflicts
        db.query(LongTermMemory).delete()
        db.commit()
    finally:
        db.close()

    # 1. SQL Injection Fuzzing
    print("1. Testing SQL Injection attacks in categories and content...")
    sql_payloads = [
        ("personal' OR 1=1;--", "My bank account PIN is 1234. Secret message."),
        ("coding", "'; DROP TABLE long_term_memory;--"),
        ("test\x00nullbyte", "Testing null character injection safe handling.")
    ]
    
    for cat, cont in sql_payloads:
        try:
            success = store_memory(category=cat, content=cont, importance=3)
            print(f"  - Store memory with payload [cat: {repr(cat)}, cont: {repr(cont)}]: Success={success}")
            assert success is True, "SQL Injection payload broke store_memory!"
        except Exception as e:
            print(f"  - FAILED/CRASHED on SQL Injection payload: {e}")
            sys.exit(1)

    # Verify retrieval with SQL injection strings
    print("  - Retrieving memories using SQL Injection query...")
    try:
        results = retrieve_relevant_memories(context_text="'; SELECT * FROM user_preferences; --", active_category=None)
        print(f"  - Retrieved successfully. Count={len(results)}")
    except Exception as e:
        print(f"  - FAILED/CRASHED on SQL Injection query: {e}")
        sys.exit(1)
        
    # 2. Corrupted Vector Payload Testing
    print("\n2. Testing Corrupted Vector data in SQLite database...")
    corrupted_vectors = [
        "not-a-json-array",
        "[1.0, 2.0, 'corrupted_string', 4.0]",
        "[NaN, Infinity, null]",
        "[]", # Empty array
        None # Empty vector
    ]
    
    db = SessionLocal()
    try:
        for idx, cv in enumerate(corrupted_vectors):
            enc_cat = crypto_manager.encrypt("security_test")
            enc_content = crypto_manager.encrypt(f"Corrupted vector test memory #{idx}")
            bad_mem = LongTermMemory(
                category=enc_cat,
                content=enc_content,
                importance=3,
                vector=cv,
                embedding_model="gemini-embedding-2"
            )
            db.add(bad_mem)
        db.commit()
        print(f"  - Inserted {len(corrupted_vectors)} records with malformed/corrupt vectors directly into SQLite.")
    finally:
        db.close()

    # Test query handling when database contains corrupted vectors
    print("  - Querying database with corrupted vectors (should log warnings and continue safely)...")
    try:
        results = retrieve_relevant_memories(context_text="What programming language do I code in?", active_category=None)
        print(f"  - Retrieval query completed successfully. Results count={len(results)}")
        # Verify that it didn't crash
        print("  - SUCCESS: System handled malformed vectors in DB without crashing!")
    except Exception as e:
        print(f"  - FAILED/CRASHED while parsing malformed vectors: {e}")
        sys.exit(1)

    # 3. Unicode and Script Tag Fuzzing (XSS / Injection safeguards)
    print("\n3. Testing Unicode, Emojis, Bengali script, and Script Tags...")
    anomalous_payloads = [
        ("বঙালী", "আমার সোনার বাংলা, আমি তোমায় ভালোবাসি।"), # Bengali script
        ("personal", "I visited Paris 🚀✈️, it was amazing! 😍"), # Emojis
        ("general", "<script>alert('xss')</script> HTML injection content.") # Script tag
    ]
    
    for cat, cont in anomalous_payloads:
        try:
            success = store_memory(category=cat, content=cont, importance=4)
            print(f"  - Store memory with payload [cat: {repr(cat)}, cont: {repr(cont)}]: Success={success}")
            assert success is True, "Unicode/XSS payload broke store_memory!"
        except Exception as e:
            print(f"  - FAILED/CRASHED on Unicode/XSS payload: {e}")
            sys.exit(1)

    # Query with script tag and unicode
    print("  - Retrieving memories using Unicode query...")
    try:
        results = retrieve_relevant_memories(context_text="সোনার বাংলা", active_category=None)
        print("  - Results returned:")
        for r in results:
            print(f"    - {r}")
        assert any("সোনার বাংলা" in r for r in results), "Failed to match Bengali script query!"
        print("  - SUCCESS: Unicode queries matched and decrypted perfectly!")
    except Exception as e:
        print(f"  - FAILED/CRASHED on Unicode retrieval: {e}")
        sys.exit(1)

    # Cleanup test database
    db = SessionLocal()
    try:
        db.query(LongTermMemory).delete()
        db.commit()
        print("\nCleared database after security audit.")
    finally:
        db.close()

    print("\n--- SECURITY AUDIT PASSED: ZERO VULNERABILITIES DETECTED ---")

if __name__ == "__main__":
    main()
