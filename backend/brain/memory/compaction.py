import json
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import logging

from ...database.connection import SessionLocal
from ...database.models import SessionMemory
from .long_term_memory import store_memory
from ..providers.gemini_adapter import gemini_adapter

logger = logging.getLogger(__name__)

ARCHIVE_DIR = "archive/conversations"

async def run_dreaming_mode(hours_threshold: int = 12):
    """
    Executes 'Dreaming Mode' for Maya.
    1. Finds all SessionMemory older than `hours_threshold`.
    2. Groups them by session_id.
    3. Feeds them to the LLM to extract facts, preferences, contacts, etc.
    4. Saves extracted facts to LongTermMemory.
    5. Archives the raw logs to a JSONL file and deletes them from the DB.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_threshold)
        
        # Get distinct old sessions
        old_sessions = db.query(SessionMemory.session_id).filter(SessionMemory.timestamp < cutoff).distinct().all()
        
        if not old_sessions:
            logger.info("[DreamingMode] No old memories to process.")
            return

        for (session_id,) in old_sessions:
            logger.info(f"[DreamingMode] Processing memories for session: {session_id}")
            
            # Fetch all old logs for this session
            logs = db.query(SessionMemory).filter(
                SessionMemory.session_id == session_id,
                SessionMemory.timestamp < cutoff
            ).order_by(SessionMemory.timestamp).all()
            
            if not logs:
                continue
                
            # Build text block for LLM
            chat_transcript = ""
            raw_dicts = []
            for log in logs:
                chat_transcript += f"{log.role.upper()}: {log.content}\n"
                raw_dicts.append({
                    "role": log.role,
                    "content": log.content,
                    "timestamp": log.timestamp.isoformat()
                })
                
            # Step 1: Prompt LLM for extraction
            extraction_prompt = f"""
You are the Memory Compaction Agent for Maya AI.
Read the following past conversation and extract any important information into specific categories:
1. preferences (user likes/dislikes)
2. contacts (names, phone numbers)
3. facts (important personal or world facts discussed)
4. projects/tasks (ongoing work)

Format your response EXACTLY as a JSON array of objects.
Example:
[
  {{"category": "preferences", "content": "User prefers dark mode", "importance": 4}},
  {{"category": "contacts", "content": "User's brother is named Rahul", "importance": 5}}
]

If there is nothing important to remember, return an empty array: []

Conversation:
{chat_transcript}
"""
            try:
                # Use Gemini flash for fast processing
                llm_response = await gemini_adapter.generate_response(
                    context=[{"role": "user", "content": extraction_prompt}],
                    prompt="",
                    override_tools=[]
                )
                
                # Cleanup markdown formatting
                if "```json" in llm_response:
                    llm_response = llm_response.split("```json")[1].split("```")[0].strip()
                elif "```" in llm_response:
                    llm_response = llm_response.split("```")[1].strip()
                    
                extracted_memories = json.loads(llm_response)
                
                # Save to LongTermMemory
                for mem in extracted_memories:
                    cat = mem.get("category", "facts")
                    cont = mem.get("content", "")
                    imp = mem.get("importance", 3)
                    
                    if cont:
                        store_memory(category=cat, content=cont, importance=imp, source_session_id=session_id)
                
            except Exception as e:
                logger.error(f"[DreamingMode] Failed to extract memories for {session_id}: {e}")
                # We do not archive/delete if extraction failed, to try again later
                continue
                
            # Step 2: Archive raw logs
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            archive_path = os.path.join(ARCHIVE_DIR, f"{session_id}.jsonl")
            with open(archive_path, "a", encoding="utf-8") as f:
                for rd in raw_dicts:
                    f.write(json.dumps(rd, ensure_ascii=False) + "\n")
                    
            # Step 3: Delete from SQLite to keep it lightweight
            for log in logs:
                db.delete(log)
            
            db.commit()
            logger.info(f"[DreamingMode] Successfully compacted and archived {len(logs)} messages for {session_id}.")
            
    except Exception as e:
        logger.error(f"[DreamingMode] Fatal error during dreaming: {e}")
    finally:
        db.close()
