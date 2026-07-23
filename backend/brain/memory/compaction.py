import hashlib
import json
import os
from pathlib import Path
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import logging

from ...database.connection import SessionLocal
from ...database.models import SessionMemory
from ...config.runtime_paths import DATA_DIR, PROJECT_ROOT
from .long_term_memory import store_memory
from .session_security import (
    decrypt_session_content,
    encrypt_session_content,
    opaque_session_id,
)
from ..providers.gemini_adapter import gemini_adapter

logger = logging.getLogger(__name__)

_DEFAULT_ARCHIVE_DIR = DATA_DIR / "archive" / "conversations"
_DEFAULT_LEGACY_ARCHIVE_DIR = PROJECT_ROOT / "archive" / "conversations"
ARCHIVE_DIR = _DEFAULT_ARCHIVE_DIR
LEGACY_ARCHIVE_DIR = _DEFAULT_LEGACY_ARCHIVE_DIR
MAX_LEGACY_ARCHIVE_BYTES = 16 * 1024 * 1024


def migrate_legacy_archives() -> int:
    """Move project-local plaintext archives into verified encrypted envelopes."""
    legacy_dir = Path(LEGACY_ARCHIVE_DIR)
    if not legacy_dir.is_dir():
        return 0

    archive_dir = Path(ARCHIVE_DIR)
    if (
        legacy_dir.resolve() == Path(_DEFAULT_LEGACY_ARCHIVE_DIR).resolve()
        and archive_dir.resolve() != Path(_DEFAULT_ARCHIVE_DIR).resolve()
    ):
        logger.error(
            "[DreamingMode] Refusing legacy migration to a non-default destination."
        )
        return 0
    archive_dir.mkdir(parents=True, exist_ok=True)
    migrated = 0

    for source_path in legacy_dir.glob("*.jsonl"):
        if source_path.is_symlink() or not source_path.is_file():
            continue
        session_ref = opaque_session_id(source_path.stem)
        temp_path = None
        try:
            if source_path.stat().st_size > MAX_LEGACY_ARCHIVE_BYTES:
                logger.error("[DreamingMode] Legacy archive exceeds the migration size limit.")
                continue

            source_bytes = source_path.read_bytes()
            plaintext = source_bytes.decode("utf-8")
            digest = hashlib.sha256(source_bytes).hexdigest()
            envelope = {
                "version": 1,
                "legacy_name": source_path.name,
                "sha256": digest,
                "raw_jsonl": plaintext,
            }
            encrypted_record = encrypt_session_content(
                json.dumps(envelope, ensure_ascii=False)
            )
            temp_path = archive_dir / f".{session_ref}.{uuid.uuid4().hex}.tmp"
            destination = archive_dir / f"legacy-{session_ref}.jsonl.enc"
            with open(temp_path, "x", encoding="utf-8") as handle:
                handle.write(encrypted_record + "\n")
                handle.flush()
                os.fsync(handle.fileno())

            stored_record = json.loads(
                decrypt_session_content(temp_path.read_text(encoding="utf-8").strip())
            )
            stored_text = stored_record.get("raw_jsonl", "")
            if (
                stored_record.get("sha256") != digest
                or hashlib.sha256(stored_text.encode("utf-8")).hexdigest() != digest
            ):
                raise ValueError("Encrypted archive migration verification failed.")

            if hashlib.sha256(source_path.read_bytes()).hexdigest() != digest:
                raise ValueError("Legacy archive changed during migration.")
            os.replace(temp_path, destination)
            source_path.unlink()
            migrated += 1
        except Exception as exc:
            logger.error(
                "[DreamingMode] Could not migrate legacy archive %s: %s",
                session_ref,
                exc,
            )
            try:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    return migrated

async def run_dreaming_mode(hours_threshold: int = 12):
    """
    Executes 'Dreaming Mode' for Maya.
    1. Finds all SessionMemory older than `hours_threshold`.
    2. Groups them by session_id.
    3. Feeds them to the LLM to extract facts, preferences, contacts, etc.
    4. Saves extracted facts to LongTermMemory.
    5. Archives the raw logs as encrypted JSONL and deletes them from the DB.
    """
    migrate_legacy_archives()
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_threshold)
        
        # Get distinct old sessions
        old_sessions = db.query(SessionMemory.session_id).filter(SessionMemory.timestamp < cutoff).distinct().all()
        
        if not old_sessions:
            logger.info("[DreamingMode] No old memories to process.")
            return

        for (session_id,) in old_sessions:
            session_ref = opaque_session_id(session_id)
            logger.info(f"[DreamingMode] Processing memories for session: {session_ref}")
            
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
            try:
                for log in logs:
                    content = decrypt_session_content(log.content)
                    chat_transcript += f"{log.role.upper()}: {content}\n"
                    raw_dicts.append({
                        "role": log.role,
                        "content": content,
                        "timestamp": log.timestamp.isoformat()
                    })
            except ValueError as exc:
                logger.error(
                    "[DreamingMode] Skipping unreadable session %s: %s",
                    session_ref,
                    exc,
                )
                continue
                
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
                llm_response = (llm_response or "").strip()
                if "```json" in llm_response:
                    llm_response = llm_response.split("```json")[1].split("```")[0].strip()
                elif "```" in llm_response:
                    llm_response = llm_response.split("```")[1].strip()

                # An empty/whitespace reply (or a bare non-JSON fallback like
                # "Done.") means the model found nothing worth remembering. Treat
                # it as an empty result so the session still gets archived instead
                # of failing forever and re-processing the same session every cycle.
                if not llm_response or llm_response[0] not in "[{":
                    extracted_memories = []
                else:
                    extracted_memories = json.loads(llm_response)
                if isinstance(extracted_memories, dict):
                    extracted_memories = [extracted_memories]
                
                # Save to LongTermMemory
                for mem in extracted_memories:
                    cat = mem.get("category", "facts")
                    cont = mem.get("content", "")
                    imp = mem.get("importance", 3)
                    
                    if cont:
                        store_memory(category=cat, content=cont, importance=imp, source_session_id=session_id)
                
            except Exception as e:
                logger.error(f"[DreamingMode] Failed to extract memories for {session_ref}: {e}")
                # If extraction fails due to unparseable JSON/content, quarantine the record
                try:
                    quarantine_dir = Path(COMPACTION_DIR) / ".quarantine"
                    quarantine_dir.mkdir(parents=True, exist_ok=True)
                    quarantine_file = quarantine_dir / f"{session_ref}.jsonl"
                    with open(quarantine_file, "a", encoding="utf-8") as qf:
                        qf.write(f"// Failed: {e}\n")
                    logger.warning(f"[DreamingMode] Quarantined corrupted session reference: {session_ref}")
                except Exception as q_err:
                    logger.error(f"[DreamingMode] Failed to quarantine {session_ref}: {q_err}")
                continue
                
            # Step 2: Archive one encrypted envelope. Neither message content nor
            # the external session identifier is exposed in the path or file.
            archive_dir = Path(ARCHIVE_DIR)
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = archive_dir / f"{session_ref}.jsonl.enc"
            archive_record = {
                "version": 1,
                "session_id": session_id,
                "messages": raw_dicts,
            }
            encrypted_record = encrypt_session_content(
                json.dumps(archive_record, ensure_ascii=False)
            )
            with open(archive_path, "a", encoding="utf-8") as f:
                f.write(encrypted_record + "\n")
                    
            # Step 3: Delete from SQLite to keep it lightweight
            for log in logs:
                db.delete(log)
            
            db.commit()
            logger.info(
                f"[DreamingMode] Successfully compacted and archived "
                f"{len(logs)} messages for {session_ref}."
            )
            
    except Exception as e:
        logger.error(f"[DreamingMode] Fatal error during dreaming: {e}")
    finally:
        db.close()
