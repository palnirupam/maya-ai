import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from backend.brain.orchestrator import ConversationOrchestrator
from backend.brain.memory.compaction import (
    ARCHIVE_DIR,
    migrate_legacy_archives,
    run_dreaming_mode,
)
from backend.brain.memory.session_security import (
    decrypt_session_content,
    migrate_legacy_session_rows,
)
from backend.config.runtime_paths import DATA_DIR
from backend.database.connection import SessionLocal
from backend.database.models import SessionMemory, LongTermMemory


class TestSessionMemoryPersistence(unittest.TestCase):
    def setUp(self):
        self.session_id = "test_dreaming_persist_session"
        self.db = SessionLocal()
        self.db.query(SessionMemory).filter_by(session_id=self.session_id).delete()
        self.db.commit()

    def tearDown(self):
        self.db.query(SessionMemory).filter_by(session_id=self.session_id).delete()
        self.db.commit()
        self.db.close()

    def test_add_to_memory_persists_conversation_turns_for_dreaming_mode(self):
        orch = ConversationOrchestrator()

        with patch("backend.brain.memory.long_term_memory.build_memory_context_block", return_value=""):
            orch.add_to_memory(self.session_id, "user", "Remember that I am learning React.")
            orch.add_to_memory(self.session_id, "assistant", "Got it.")

        rows = (
            self.db.query(SessionMemory)
            .filter_by(session_id=self.session_id)
            .order_by(SessionMemory.id)
            .all()
        )
        self.assertEqual([r.role for r in rows], ["user", "assistant"])
        self.assertNotIn("learning React", rows[0].content)
        self.assertTrue(rows[0].content.startswith("enc:v1:"))
        self.assertIn("learning React", decrypt_session_content(rows[0].content))

    def test_unreadable_encrypted_content_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "could not be decrypted"):
            decrypt_session_content("enc:v1:not-a-valid-token")

    def test_legacy_plaintext_database_rows_migrate_atomically(self):
        self.db.add(SessionMemory(
            session_id=self.session_id,
            role="user",
            content="legacy private conversation",
        ))
        self.db.commit()

        self.assertEqual(
            migrate_legacy_session_rows(self.db, session_id=self.session_id),
            1,
        )
        row = self.db.query(SessionMemory).filter_by(session_id=self.session_id).one()
        self.assertNotIn("legacy private conversation", row.content)
        self.assertEqual(
            decrypt_session_content(row.content),
            "legacy private conversation",
        )


def test_default_archive_directory_is_ignored_runtime_data():
    assert Path(ARCHIVE_DIR).is_relative_to(DATA_DIR)


def test_legacy_plaintext_archive_is_removed_only_after_verified_encryption(tmp_path):
    legacy_dir = tmp_path / "legacy"
    secure_dir = tmp_path / "secure"
    legacy_dir.mkdir()
    plaintext = '{"role":"user","content":"private@example.com"}\n'
    source = legacy_dir / "telegram_123.jsonl"
    source.write_text(plaintext, encoding="utf-8")
    stored_plaintext = source.read_bytes().decode("utf-8")

    with patch("backend.brain.memory.compaction.LEGACY_ARCHIVE_DIR", legacy_dir), \
         patch("backend.brain.memory.compaction.ARCHIVE_DIR", secure_dir):
        assert migrate_legacy_archives() == 1

    assert not source.exists()
    encrypted_paths = list(secure_dir.glob("legacy-*.jsonl.enc"))
    assert len(encrypted_paths) == 1
    encrypted_text = encrypted_paths[0].read_text(encoding="utf-8")
    assert "private@example.com" not in encrypted_text
    envelope = json.loads(decrypt_session_content(encrypted_text.strip()))
    assert envelope["raw_jsonl"] == stored_plaintext


def test_default_legacy_source_refuses_a_redirected_destination(tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    source = legacy_dir / "desktop_native_session.jsonl"
    source.write_text("private", encoding="utf-8")

    with patch("backend.brain.memory.compaction.LEGACY_ARCHIVE_DIR", legacy_dir), \
         patch("backend.brain.memory.compaction._DEFAULT_LEGACY_ARCHIVE_DIR", legacy_dir), \
         patch("backend.brain.memory.compaction.ARCHIVE_DIR", tmp_path / "redirected"):
        assert migrate_legacy_archives() == 0

    assert source.exists()


def test_legacy_migration_failure_keeps_the_plaintext_source(tmp_path):
    legacy_dir = tmp_path / "legacy"
    secure_dir = tmp_path / "secure"
    legacy_dir.mkdir()
    source = legacy_dir / "desktop_native_session.jsonl"
    source.write_text("private", encoding="utf-8")

    with patch("backend.brain.memory.compaction.LEGACY_ARCHIVE_DIR", legacy_dir), \
         patch("backend.brain.memory.compaction.ARCHIVE_DIR", secure_dir), \
         patch("backend.brain.memory.compaction.decrypt_session_content", side_effect=ValueError("verify failed")):
        assert migrate_legacy_archives() == 0

    assert source.read_text(encoding="utf-8") == "private"
    assert not list(secure_dir.glob("legacy-*.jsonl.enc"))


class TestStreamingSessionMemoryPersistence(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session_id = "test_dreaming_stream_session"
        self.db = SessionLocal()
        self.db.query(SessionMemory).filter_by(session_id=self.session_id).delete()
        self.db.commit()

    async def asyncTearDown(self):
        self.db.query(SessionMemory).filter_by(session_id=self.session_id).delete()
        self.db.commit()
        self.db.close()

    async def test_streaming_workflow_persists_assistant_output_for_dreaming_mode(self):
        orch = ConversationOrchestrator()

        async def fake_execute_workflow(*_args, **_kwargs):
            yield "Eta "
            yield "mone rakhchi."

        with patch("backend.brain.memory.long_term_memory.build_memory_context_block", return_value=""), \
             patch("backend.brain.agents.agent_team.execute_workflow", fake_execute_workflow), \
             patch("backend.system.observability.observability.log", new=AsyncMock()):
            chunks = []
            async for chunk in orch.process_user_input_stream(
                self.session_id,
                "eta mone rekho",
            ):
                if isinstance(chunk, str):
                    chunks.append(chunk)

        self.assertEqual("".join(chunks), "Eta mone rakhchi.")
        rows = (
            self.db.query(SessionMemory)
            .filter_by(session_id=self.session_id)
            .order_by(SessionMemory.id)
            .all()
        )
        self.assertEqual([r.role for r in rows], ["user", "assistant"])
        self.assertNotIn("Eta mone rakhchi.", rows[1].content)
        self.assertEqual(
            decrypt_session_content(rows[1].content),
            "Eta mone rakhchi.",
        )


class TestDreamingModeCompaction(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session_id = "test_dreaming_compaction_session"
        self.db = SessionLocal()
        self.db.query(SessionMemory).filter_by(session_id=self.session_id).delete()
        self.db.query(LongTermMemory).filter_by(source_session_id=self.session_id).delete()
        self.db.commit()

    async def asyncTearDown(self):
        self.db.query(SessionMemory).filter_by(session_id=self.session_id).delete()
        self.db.query(LongTermMemory).filter_by(source_session_id=self.session_id).delete()
        self.db.commit()
        self.db.close()

    async def test_run_dreaming_mode_extracts_archives_and_deletes_old_session_rows(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=24)
        self.db.add_all([
            SessionMemory(
                session_id=self.session_id,
                role="user",
                content="My brother Rahul's number is +919876543210.",
                timestamp=old_time,
            ),
            SessionMemory(
                session_id=self.session_id,
                role="assistant",
                content="Saved Rahul's contact.",
                timestamp=old_time,
            ),
        ])
        self.db.commit()

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("backend.brain.memory.compaction.ARCHIVE_DIR", tmp_dir), \
             patch("backend.brain.memory.compaction.LEGACY_ARCHIVE_DIR", Path(tmp_dir) / "no-legacy-data"), \
             patch("backend.brain.memory.compaction.gemini_adapter.generate_response", new=AsyncMock(return_value='[{"category":"contacts","content":"Rahul: +919876543210","importance":5}]')), \
             patch("backend.brain.memory.compaction.store_memory", return_value=True) as mock_store:
            await run_dreaming_mode(hours_threshold=12)

            self.assertEqual(
                self.db.query(SessionMemory).filter_by(session_id=self.session_id).count(),
                0,
            )
            mock_store.assert_called_once_with(
                category="contacts",
                content="Rahul: +919876543210",
                importance=5,
                source_session_id=self.session_id,
            )
            archive_paths = list(Path(tmp_dir).glob("*.jsonl.enc"))
            self.assertEqual(len(archive_paths), 1)
            self.assertNotIn(self.session_id, archive_paths[0].name)
            archived_text = archive_paths[0].read_text(encoding="utf-8")
            self.assertNotIn("Rahul", archived_text)
            self.assertNotIn("+919876543210", archived_text)

            encrypted_lines = archived_text.splitlines()
            self.assertEqual(len(encrypted_lines), 1)
            archive_record = json.loads(decrypt_session_content(encrypted_lines[0]))
            self.assertEqual(archive_record["session_id"], self.session_id)
            self.assertEqual(len(archive_record["messages"]), 2)


if __name__ == "__main__":
    unittest.main()
