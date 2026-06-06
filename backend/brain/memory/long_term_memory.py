from datetime import datetime, timedelta, timezone
from sqlalchemy import or_
from ...database.connection import SessionLocal
from ...database.models import LongTermMemory
from ...database.crypto import crypto_manager
import logging
import json
import numpy as np

logger = logging.getLogger(__name__)

def _get_embedding(text: str) -> list[float] | None:
    """Generates embedding vector using gemini-embedding-2."""
    try:
        from ..providers.gemini_adapter import gemini_adapter
        if not gemini_adapter or not gemini_adapter.client:
            logger.warning("Gemini adapter or client not available for embedding.")
            return None
        response = gemini_adapter.client.models.embed_content(
            model='gemini-embedding-2',
            contents=text
        )
        if hasattr(response, 'embeddings') and response.embeddings:
            return response.embeddings[0].values
        elif hasattr(response, 'embedding') and response.embedding:
            return response.embedding.values
        return None
    except Exception as e:
        logger.warning(f"Failed to generate embedding from Gemini API: {e}")
        return None

def store_memory(category: str, content: str, importance: int = 3, source_session_id: str = None) -> bool:
    """Stores a memory encrypted in the database. Generates and stores its embedding."""
    db = SessionLocal()
    try:
        encrypted_category = crypto_manager.encrypt(category.lower())
        encrypted_content = crypto_manager.encrypt(content)
        
        expires_at = None
        if importance <= 2:
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)
            
        # Try to generate embedding
        vector_str = None
        embedding_model = None
        try:
            vector_vals = _get_embedding(content)
            if vector_vals:
                vector_str = json.dumps(vector_vals)
                embedding_model = 'gemini-embedding-2'
        except Exception as embed_err:
            logger.warning(f"Non-blocking embedding failure in store_memory: {embed_err}")

        new_memory = LongTermMemory(
            category=encrypted_category,
            content=encrypted_content,
            importance=importance,
            expires_at=expires_at,
            source_session_id=source_session_id,
            vector=vector_str,
            embedding_model=embedding_model
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
    """
    Retrieves relevant memories using semantic search and cosine similarity.
    Balances relevance with importance. Fallbacks to keyword matching on failures.
    """
    SIMILARITY_THRESHOLD = 0.45
    TOP_K = 8
    MAX_BACKFILL_PER_QUERY = 5
    
    db = SessionLocal()
    try:
        query = db.query(LongTermMemory)
        memories = query.all()
        
        # Determine if we should attempt semantic search
        query_vector = None
        if context_text and len(context_text.strip()) > 0:
            query_vector = _get_embedding(context_text)
            
        # Fallback keyword logic setup
        keywords = set(word.lower() for word in context_text.split() if len(word) > 3) if context_text else set()
        
        results_with_scores = []
        backfill_updates = []
        
        for mem in memories:
            try:
                decrypted_category = crypto_manager.decrypt(mem.category)
                decrypted_content = crypto_manager.decrypt(mem.content)
                
                # Apply active category filter first (if provided)
                if active_category and decrypted_category != active_category.lower():
                    # Check if importance is high enough to bypass category filter
                    if mem.importance < 4:
                        continue
                
                # Check for legacy memories that need backfill
                mem_vector = None
                if query_vector is not None:
                    if not mem.vector or mem.embedding_model != 'gemini-embedding-2':
                        if len(backfill_updates) < MAX_BACKFILL_PER_QUERY:
                            logger.info(f"Backfilling vector on-the-fly for memory ID {mem.id}")
                            new_vector_vals = _get_embedding(decrypted_content)
                            if new_vector_vals:
                                mem.vector = json.dumps(new_vector_vals)
                                mem.embedding_model = 'gemini-embedding-2'
                                backfill_updates.append(mem)
                                mem_vector = new_vector_vals
                    else:
                        try:
                            mem_vector = json.loads(mem.vector)
                        except Exception as parse_err:
                            logger.warning(f"Corrupted vector JSON for memory ID {mem.id}: {parse_err}")
                            mem_vector = None
                
                # If we successfully have both query and memory vectors, calculate cosine similarity
                if query_vector is not None and mem_vector is not None:
                    try:
                        # Ensure lists contain only numbers (no None/null elements)
                        if any(x is None for x in query_vector) or any(x is None for x in mem_vector):
                            raise ValueError("Vector contains null elements")
                        
                        a = np.array(query_vector, dtype=float)
                        b = np.array(mem_vector, dtype=float)
                        
                        if not np.isfinite(a).all() or not np.isfinite(b).all():
                            raise ValueError("Vector contains non-finite elements (NaN/Inf)")
                        
                        # Robust cosine similarity: dot(a, b) / (||a|| * ||b||)
                        norm_a = np.linalg.norm(a)
                        norm_b = np.linalg.norm(b)
                        if norm_a > 0 and norm_b > 0:
                            similarity = np.dot(a, b) / (norm_a * norm_b)
                        else:
                            similarity = 0.0
                    except Exception as math_err:
                        logger.warning(f"Error computing cosine similarity for memory ID {mem.id}: {math_err}")
                        similarity = 0.0
                    
                    # Filtering gate: must have at least 0.30 similarity OR critical importance (5)
                    if similarity >= 0.30 or mem.importance == 5:
                        # Apply importance boost to score
                        score = similarity + (mem.importance * 0.05)
                        if score >= SIMILARITY_THRESHOLD or mem.importance == 5:
                            results_with_scores.append((score, decrypted_content, mem))
                else:
                    # Fallback keyword matching (or standard return all if query is empty)
                    if keywords:
                        content_lower = decrypted_content.lower()
                        if not any(k in content_lower for k in keywords):
                            if mem.importance < 5:
                                continue
                    # Set a default dummy score based on importance for ranking fallbacks
                    score = 0.1 + (mem.importance * 0.05)
                    results_with_scores.append((score, decrypted_content, mem))
                    
            except Exception as e:
                logger.error(f"Error processing memory {mem.id}: {e}")
                continue
        
        # Batch save any backfilled vectors
        if backfill_updates:
            try:
                db.commit()
                logger.info(f"Successfully batch-committed {len(backfill_updates)} backfilled vectors.")
            except Exception as commit_err:
                logger.error(f"Failed to save backfilled vectors: {commit_err}")
                db.rollback()
                
        # Sort candidates by score descending
        results_with_scores.sort(key=lambda x: x[0], reverse=True)
        top_candidates = results_with_scores[:TOP_K]
        
        # Record analytics for retrieved candidates
        retrieved_memories = []
        for score, content, mem in top_candidates:
            retrieved_memories.append(content)
            try:
                mem.retrieval_count = (mem.retrieval_count or 0) + 1
                mem.last_accessed = datetime.now(timezone.utc)
            except Exception as anal_err:
                logger.warning(f"Failed updating retrieval analytics for memory ID {mem.id}: {anal_err}")
                
        if top_candidates:
            try:
                db.commit()
            except Exception as commit_err:
                logger.error(f"Failed committing retrieval analytics: {commit_err}")
                db.rollback()
                
        return retrieved_memories
        
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
