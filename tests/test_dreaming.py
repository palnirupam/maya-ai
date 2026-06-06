import asyncio
import os
import logging
from datetime import datetime, timezone, timedelta

# Suppress debug logs
logging.basicConfig(level=logging.WARNING)

from backend.database.connection import SessionLocal
from backend.database.models import SessionMemory, LongTermMemory
from backend.brain.memory.compaction import run_dreaming_mode
from backend.database.crypto import crypto_manager

async def test():
    db = SessionLocal()
    test_session = "test_dreaming_session_123"
    try:
        # Ensure clean state
        db.query(SessionMemory).filter_by(session_id=test_session).delete()
        db.query(LongTermMemory).filter_by(source_session_id=test_session).delete()
        db.commit()
        
        # 1. Insert fake old chat
        old_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        m1 = SessionMemory(session_id=test_session, role="user", content="Hi Maya, I am learning React right now.", timestamp=old_time)
        m2 = SessionMemory(session_id=test_session, role="assistant", content="That's great! React is awesome.", timestamp=old_time)
        m3 = SessionMemory(session_id=test_session, role="user", content="By the way, my brother's name is Rahul and his phone number is +919876543210. Can you save that?", timestamp=old_time)
        m4 = SessionMemory(session_id=test_session, role="assistant", content="Got it, I have saved Rahul's contact.", timestamp=old_time)
        
        db.add_all([m1, m2, m3, m4])
        db.commit()
        
        print(f"--- TEST 1: Inserted {db.query(SessionMemory).filter_by(session_id=test_session).count()} fake old chat logs. ---")
        
        # 2. Run dreaming mode
        print("\n--- TEST 2: Running Dreaming Mode... ---")
        await run_dreaming_mode(hours_threshold=12)
        
        # 3. Verify SessionMemory is deleted
        count = db.query(SessionMemory).filter_by(session_id=test_session).count()
        print(f"\nSessionMemory count for test session after compaction: {count} (Expected: 0)")
        
        # 4. Verify LongTermMemory extraction
        ltm = db.query(LongTermMemory).filter_by(source_session_id=test_session).all()
        print(f"\nExtracted {len(ltm)} Long Term Memories:")
        for mem in ltm:
            cat = crypto_manager.decrypt(mem.category)
            content = crypto_manager.decrypt(mem.content)
            print(f" - [{cat}] {content} (Importance: {mem.importance})")
            
        # 5. Verify archive file
        archive_path = f"archive/conversations/{test_session}.jsonl"
        if os.path.exists(archive_path):
            print(f"\nSUCCESS: Archive file created successfully at {archive_path}")
            with open(archive_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                print(f" - Contains {len(lines)} JSON lines.")
            # Cleanup archive
            os.remove(archive_path)
        else:
            print(f"\nFAILED: Archive file not found at {archive_path}")
            
    finally:
        # Cleanup DB
        db.query(SessionMemory).filter_by(session_id=test_session).delete()
        db.query(LongTermMemory).filter_by(source_session_id=test_session).delete()
        db.commit()
        db.close()

if __name__ == "__main__":
    asyncio.run(test())
