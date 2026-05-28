from datetime import datetime, timedelta, timezone
from sqlalchemy import or_
from ...database.connection import SessionLocal
from ...database.models import LongTermMemory
from ...database.crypto import crypto_manager
import logging

logger = logging.getLogger(__name__)

def store_memory(category: str, content: str, importance: int = 3, source_session_id: str = None) -> bool:
    """Stores a memory encrypted in the database. Sets expiry for low importance facts."""
    db = SessionLocal()
    try:
        encrypted_category = crypto_manager.encrypt(category.lower())
        encrypted_content = crypto_manager.encrypt(content)
        
        expires_at = None
        if importance <= 2:
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)
            
        new_memory = LongTermMemory(
            category=encrypted_category,
            content=encrypted_content,
            importance=importance,
            expires_at=expires_at,
            source_session_id=source_session_id
        )
        db.add(new_memory)
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        return False
    finally:
        db.close()

def retrieve_relevant_memories(context_text: str = "", active_category: str = None) -> list[str]:
    """Retrieves relevant memories. Prioritizes category, then filters by keywords."""
    db = SessionLocal()
    try:
        query = db.query(LongTermMemory)
        memories = query.all()
        
        results = []
        keywords = set(word.lower() for word in context_text.split() if len(word) > 3)
        
        for mem in memories:
            try:
                decrypted_category = crypto_manager.decrypt(mem.category)
                decrypted_content = crypto_manager.decrypt(mem.content)
                
                # Filter by active category first (if provided)
                if active_category and decrypted_category != active_category.lower():
                    # Check if importance is high enough to bypass category filter
                    if mem.importance < 4:
                        continue
                        
                # Filter by keyword if there are keywords
                if keywords:
                    content_lower = decrypted_content.lower()
                    if not any(k in content_lower for k in keywords):
                        # Skip if it doesn't match any keyword, unless it's critical importance
                        if mem.importance < 5:
                            continue
                            
                results.append(decrypted_content)
            except Exception as e:
                logger.error(f"Error decrypting memory {mem.id}: {e}")
                continue
                
        return results
    finally:
        db.close()

def cleanup_expired_memories():
    """Deletes expired memories from the database."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        expired = db.query(LongTermMemory).filter(
            LongTermMemory.expires_at != None,
            LongTermMemory.expires_at < now
        ).all()
        
        if expired:
            for mem in expired:
                db.delete(mem)
            db.commit()
            logger.info(f"Cleaned up {len(expired)} expired memories.")
    except Exception as e:
        logger.error(f"Failed to cleanup expired memories: {e}")
    finally:
        db.close()

def build_memory_context_block(active_category: str = None, context_text: str = "") -> str:
    """Builds a formatted string of memories to inject into the system prompt."""
    memories = retrieve_relevant_memories(context_text, active_category)
    if not memories:
        return ""
        
    block = "<long_term_memory>\n"
    for mem in memories:
        block += f"- {mem}\n"
    block += "</long_term_memory>\n"
    return block
