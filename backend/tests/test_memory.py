"""Security-fuzz regression tests for the encrypted vector memory system.

Bug: README claims the memory database was "Evaluated against threat models
including SQL Injection, null-byte input, non-finite vector parameters
(NaN/Infinity), corrupted vector JSON, and Unicode/XSS script tag injections
to guarantee zero backend crashes" — but this test file was completely empty,
so that claim had zero regression coverage. The defensive code in
long_term_memory.py already handles these cases; these tests just prove it
and lock the behavior in.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from backend.database.crypto import crypto_manager
from backend.database.models import LongTermMemory
from backend.brain.memory.long_term_memory import store_memory, retrieve_relevant_memories
from backend.config.model_config import get_model


class _FakeMemRow:
    """Minimal stand-in for a LongTermMemory ORM row."""

    def __init__(self, id, category, content, importance, vector=None, embedding_model=None):
        self.id = id
        self.category = category
        self.content = content
        self.importance = importance
        self.vector = vector
        self.embedding_model = embedding_model
        self.retrieval_count = 0
        self.last_accessed = None


class TestStoreMemoryFuzzing(unittest.TestCase):
    """store_memory() must never crash regardless of what's in `content`."""

    @patch('backend.brain.memory.long_term_memory._get_embedding', return_value=None)
    @patch('backend.brain.memory.long_term_memory.SessionLocal')
    def test_sql_injection_content_stored_safely(self, mock_session_local, _mock_embed):
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        malicious = "'; DROP TABLE long_term_memory; --"

        ok = store_memory(category="test", content=malicious)

        self.assertTrue(ok)
        stored = mock_db.add.call_args[0][0]
        self.assertEqual(crypto_manager.decrypt(stored.content), malicious)

    @patch('backend.brain.memory.long_term_memory._get_embedding', return_value=None)
    @patch('backend.brain.memory.long_term_memory.SessionLocal')
    def test_null_byte_content_stored_safely(self, mock_session_local, _mock_embed):
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        content = "hello\x00world"

        ok = store_memory(category="test", content=content)

        self.assertTrue(ok)
        stored = mock_db.add.call_args[0][0]
        self.assertEqual(crypto_manager.decrypt(stored.content), content)

    @patch('backend.brain.memory.long_term_memory._get_embedding', return_value=None)
    @patch('backend.brain.memory.long_term_memory.SessionLocal')
    def test_unicode_xss_content_stored_safely(self, mock_session_local, _mock_embed):
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        xss = "<script>alert(1)</script> — 日本語 — \U0001F600"

        ok = store_memory(category="test", content=xss)

        self.assertTrue(ok)
        stored = mock_db.add.call_args[0][0]
        self.assertEqual(crypto_manager.decrypt(stored.content), xss)


class TestRetrieveMemoryFuzzing(unittest.TestCase):
    """retrieve_relevant_memories() must degrade gracefully — never crash —
    on non-finite vectors, corrupted vector JSON, or hostile content."""

    @patch('backend.brain.memory.long_term_memory._get_embedding')
    @patch('backend.brain.memory.long_term_memory.SessionLocal')
    def test_non_finite_vector_treated_as_zero_similarity(self, mock_session_local, mock_get_embedding):
        mock_get_embedding.return_value = [1.0, 0.0, 0.0]
        expected_model = get_model("embedding_cloud")
        row = _FakeMemRow(
            id=1,
            category=crypto_manager.encrypt("test"),
            content=crypto_manager.encrypt("has a NaN/Infinity vector"),
            importance=3,
            vector=json.dumps([float("nan"), float("inf"), 2.0]),
            embedding_model=expected_model,
        )
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [row]
        mock_session_local.return_value = mock_db

        results = retrieve_relevant_memories(context_text="some query")

        self.assertEqual(results, [])  # similarity forced to 0, importance 3 < 5 -> excluded, no crash

    @patch('backend.brain.memory.long_term_memory._get_embedding')
    @patch('backend.brain.memory.long_term_memory.SessionLocal')
    def test_corrupted_vector_json_falls_back_gracefully(self, mock_session_local, mock_get_embedding):
        mock_get_embedding.return_value = [1.0, 0.0, 0.0]
        expected_model = get_model("embedding_cloud")
        row = _FakeMemRow(
            id=2,
            category=crypto_manager.encrypt("test"),
            content=crypto_manager.encrypt("has corrupted vector JSON"),
            importance=3,
            vector="not-valid-json{{{",
            embedding_model=expected_model,
        )
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [row]
        mock_session_local.return_value = mock_db

        results = retrieve_relevant_memories(context_text="some query")  # must not raise

        self.assertEqual(results, [])

    @patch('backend.brain.memory.long_term_memory._get_embedding', return_value=None)
    @patch('backend.brain.memory.long_term_memory.SessionLocal')
    def test_xss_content_returned_verbatim_not_executed(self, mock_session_local, _mock_embed):
        xss = "<script>alert(1)</script>"
        row = _FakeMemRow(
            id=3,
            category=crypto_manager.encrypt("test"),
            content=crypto_manager.encrypt(xss),
            importance=5,
        )
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [row]
        mock_session_local.return_value = mock_db

        results = retrieve_relevant_memories(context_text="")

        self.assertIn(xss, results)  # stored/returned as inert text, never interpreted


if __name__ == "__main__":
    unittest.main()
