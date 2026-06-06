import os
import sys
import time
from datetime import datetime, timezone

# Add backend to path
sys.path.append("c:\\maya-ai")
from backend.database.connection import SessionLocal, engine
from backend.database.models import LongTermMemory, UserPreferences
from backend.database.crypto import crypto_manager
from backend.brain.memory.long_term_memory import store_memory, retrieve_relevant_memories

def clear_test_memories():
    db = SessionLocal()
    try:
        # We delete all memories to start fresh
        db.query(LongTermMemory).delete()
        db.commit()
        print("Cleared existing long term memory for clean testing.")
    finally:
        db.close()

def print_all_memories_db():
    db = SessionLocal()
    try:
        mems = db.query(LongTermMemory).all()
        print(f"\n--- Current Database State ({len(mems)} records) ---")
        for m in mems:
            cat = crypto_manager.decrypt(m.category)
            content = crypto_manager.decrypt(m.content)
            has_vector = m.vector is not None
            vector_len = len(eval(m.vector)) if m.vector else 0
            print(f"ID: {m.id} | Cat: {cat} | Content: '{content}' | Importance: {m.importance} | Has Vector: {has_vector} (len={vector_len}) | Model: {m.embedding_model} | Accesses: {m.retrieval_count}")
        print("--------------------------------------------------\n")
    finally:
        db.close()

def main():
    print("Starting Vector Memory Verification tests...\n")
    clear_test_memories()
    
    # 1. Test memory storage with active gemini API key
    print("1. Storing test memories...")
    # These should successfully generate and store gemini-embedding-2 vectors
    m1_success = store_memory(category="personal", content="I love drinking Earl Grey tea in the morning.", importance=3)
    m2_success = store_memory(category="coding", content="My favorite programming language is Python.", importance=4)
    m3_success = store_memory(category="personal", content="I met my friend Rahul yesterday in the park.", importance=3)
    m4_success = store_memory(category="general", content="The capital city of France is Paris.", importance=1)
    
    print(f"Stored memories status: M1={m1_success}, M2={m2_success}, M3={m3_success}, M4={m4_success}")
    print_all_memories_db()
    
    # 2. Test semantic search (similar wording but different phrasing)
    print("2. Querying memory semantically: 'What hot breakfast beverages do I like?'")
    results = retrieve_relevant_memories(context_text="What hot breakfast beverages do I like?", active_category=None)
    print("Results returned:")
    for r in results:
        print(f"  - {r}")
    assert any("Earl Grey" in r for r in results), "Failed to retrieve Earl Grey tea memory semantically!"
    print("Semantic search for Earl Grey tea succeeded!\n")
    
    # 3. Test semantic search with active category filter
    print("3. Querying coding memories: 'What language do I code in?' with active_category='coding'")
    results = retrieve_relevant_memories(context_text="What language do I code in?", active_category="coding")
    print("Results returned:")
    for r in results:
        print(f"  - {r}")
    assert any("Python" in r for r in results), "Failed to retrieve Python memory with category filter!"
    assert not any("Earl Grey" in r for r in results), "Category filter failed to exclude Earl Grey!"
    print("Category filtering with semantic search succeeded!\n")
    
    # 4. Test legacy / manual vector backfilling on-the-fly
    print("4. Simulating legacy memory (no vector)...")
    db = SessionLocal()
    try:
        # Create a memory record manually without vector to simulate a legacy record
        enc_cat = crypto_manager.encrypt("personal")
        enc_content = crypto_manager.encrypt("My grandmother's name is Nabanita.")
        legacy_mem = LongTermMemory(
            category=enc_cat,
            content=enc_content,
            importance=3,
            vector=None,
            embedding_model=None
        )
        db.add(legacy_mem)
        db.commit()
        legacy_id = legacy_mem.id
        print(f"Created legacy memory ID: {legacy_id}")
    finally:
        db.close()
        
    print_all_memories_db()
    
    # Query with something semantically close to grandmother's name
    print(f"Querying: 'Who is Nabanita?' (should trigger on-the-fly backfill for memory {legacy_id})")
    results = retrieve_relevant_memories(context_text="Who is Nabanita?", active_category=None)
    print("Results returned:")
    for r in results:
        print(f"  - {r}")
    assert any("Nabanita" in r for r in results), "Failed to retrieve legacy memory!"
    
    # Verify that it is now backfilled in DB
    db = SessionLocal()
    try:
        updated_mem = db.query(LongTermMemory).filter(LongTermMemory.id == legacy_id).first()
        assert updated_mem.vector is not None, "Failed to backfill vector on-the-fly!"
        assert updated_mem.embedding_model == 'gemini-embedding-2', "Embedding model not updated!"
        print(f"Successfully verified on-the-fly vector backfill for legacy memory!")
    finally:
        db.close()
        
    print_all_memories_db()
    
    # 5. Verify analytics tracking (retrieval count and last_accessed)
    print("5. Verifying retrieval analytics...")
    db = SessionLocal()
    try:
        m1 = db.query(LongTermMemory).filter(LongTermMemory.id == 1).first()
        print(f"Memory 1 ('Earl Grey') - Retrieval Count: {m1.retrieval_count}, Last Accessed: {m1.last_accessed}")
        assert m1.retrieval_count > 0, "Retrieval count was not incremented!"
        assert m1.last_accessed is not None, "Last accessed time was not updated!"
        print("Retrieval analytics verification succeeded!\n")
    finally:
        db.close()
        
    # 6. Verify non-blocking behavior of embedding failures
    print("6. Verifying non-blocking behavior on embedding failures...")
    # We will simulate an environment where gemini adapter api key is temporarily broken or raises an exception
    # (By monkey-patching _get_embedding temporarily in this script context)
    import backend.brain.memory.long_term_memory as ltm
    original_get_embedding = ltm._get_embedding
    
    try:
        # Monkey patch to return None (simulate failure)
        ltm._get_embedding = lambda text: None
        print("Simulated embedding API offline (returns None). Storing new memory...")
        offline_success = ltm.store_memory(category="general", content="Offline memory without a vector.", importance=3)
        print(f"Offline store memory success: {offline_success}")
        assert offline_success is True, "Offline store memory failed!"
        
        # Verify it exists in DB with None vector
        db = SessionLocal()
        try:
            off_mem = db.query(LongTermMemory).order_by(LongTermMemory.id.desc()).first()
            decrypted_off = crypto_manager.decrypt(off_mem.content)
            print(f"Offline memory in DB: '{decrypted_off}' | Vector: {off_mem.vector} | Model: {off_mem.embedding_model}")
            assert off_mem.vector is None, "Vector should be None for offline memory!"
            assert off_mem.embedding_model is None, "Embedding model should be None for offline memory!"
            print("Offline non-blocking storage verification succeeded!\n")
        finally:
            db.close()
            
        # Verify retrieval falls back successfully when embedding is offline
        print("Querying memories while embedding API is offline...")
        results_offline = ltm.retrieve_relevant_memories(context_text="Offline memory", active_category=None)
        print("Offline query results returned (fallback keyword matching):")
        for r in results_offline:
            print(f"  - {r}")
        assert any("Offline memory" in r for r in results_offline), "Fallback keyword matching failed to retrieve memory!"
        print("Fallback keyword retrieval while offline succeeded!\n")
        
    finally:
        # Restore original function
        ltm._get_embedding = original_get_embedding

    print("ALL TESTS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
