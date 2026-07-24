"""
Sprint 0 — Industry-level regression suite.

Tests the two P0/P1 performance fixes:
  1. TTSRouter      : default="edge", provider validation, async fallback chain
  2. LongTermMemory : LRU embedding cache hit/miss, DB-level filter+order+limit

Standard applied:
  - One behaviour per test
  - Deterministic — no randomness, no real network
  - Isolated — LRU cache cleared in setUp/tearDown
  - Fast — all external I/O mocked

Run:
    python -m pytest backend/tests/test_sprint0_deep.py -v
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from backend.brain.memory.long_term_memory import (
    _DB_LOAD_LIMIT,
    _get_embedding,
    _get_embedding_cached,
    retrieve_relevant_memories,
)
from backend.database.crypto import crypto_manager
from backend.voice.output.tts_router import (
    _DEFAULT_TTS_PROVIDER,
    _VALID_TTS_PROVIDERS,
    TTSRouter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeRow:
    """Minimal duck-type stand-in for a LongTermMemory ORM row."""
    def __init__(self, *, content, importance=3, category="test", vector=None):
        self.id = 1
        self.category = crypto_manager.encrypt(category)
        self.content = crypto_manager.encrypt(content)
        self.importance = importance
        self.vector = vector
        self.retrieval_count = 0
        self.last_accessed = None
        self.expires_at = None


def _mock_db_with_rows(*rows):
    mock_db = MagicMock()
    (mock_db.query.return_value
           .filter.return_value
           .order_by.return_value
           .limit.return_value
           .all.return_value) = list(rows)
    return mock_db


def _build_router(stored_provider=None, decrypt_raises=False):
    with (
        patch("backend.voice.output.tts_router.EdgeTTSAdapter"),
        patch("backend.voice.output.tts_router.GPTSoVITSAdapter"),
        patch("backend.voice.output.tts_router.ElevenLabsAdapter"),
        patch("backend.voice.output.tts_router.GeminiLiveAdapter"),
        patch("backend.voice.output.tts_router.SessionLocal") as MockSL,
        patch("backend.voice.output.tts_router.crypto_manager") as MockCM,
    ):
        mock_db = MagicMock()
        MockSL.return_value = mock_db
        if stored_provider is not None:
            pref = MagicMock()
            pref.value = "token"
            mock_db.query.return_value.filter.return_value.first.return_value = pref
            if decrypt_raises:
                MockCM.decrypt.side_effect = Exception("bad crypto")
            else:
                MockCM.decrypt.return_value = stored_provider
        else:
            mock_db.query.return_value.filter.return_value.first.return_value = None
        return TTSRouter()


# ===========================================================================
# 1. TTSRouter constants
# ===========================================================================

class TestTTSRouterConstants(unittest.TestCase):

    def test_default_provider_is_edge(self):
        self.assertEqual(_DEFAULT_TTS_PROVIDER, "edge")

    def test_valid_providers_exact_set(self):
        self.assertEqual(_VALID_TTS_PROVIDERS, {"edge", "gemini", "elevenlabs", "gpt_sovits"})

    def test_valid_providers_is_frozenset(self):
        self.assertIsInstance(_VALID_TTS_PROVIDERS, frozenset)


# ===========================================================================
# 2. TTSRouter reload_key
# ===========================================================================

class TestTTSRouterReloadKey(unittest.TestCase):

    def test_no_db_preference_uses_default(self):
        router = _build_router(stored_provider=None)
        self.assertEqual(router.primary_provider, _DEFAULT_TTS_PROVIDER)

    def test_edge_preference_honoured(self):
        router = _build_router(stored_provider="edge")
        self.assertEqual(router.primary_provider, "edge")

    def test_gemini_preference_honoured(self):
        router = _build_router(stored_provider="gemini")
        self.assertEqual(router.primary_provider, "gemini")

    def test_elevenlabs_preference_honoured(self):
        router = _build_router(stored_provider="elevenlabs")
        self.assertEqual(router.primary_provider, "elevenlabs")

    def test_gpt_sovits_preference_honoured(self):
        router = _build_router(stored_provider="gpt_sovits")
        self.assertEqual(router.primary_provider, "gpt_sovits")

    def test_unknown_stored_value_falls_back_to_default(self):
        router = _build_router(stored_provider="openai_tts")
        self.assertEqual(router.primary_provider, _DEFAULT_TTS_PROVIDER)

    def test_decrypt_failure_falls_back_to_default(self):
        router = _build_router(stored_provider="gemini", decrypt_raises=True)
        self.assertEqual(router.primary_provider, _DEFAULT_TTS_PROVIDER)

    def test_edge_not_force_upgraded_to_gemini(self):
        """REGRESSION: old code silently upgraded edge -> gemini. Must not recur."""
        router = _build_router(stored_provider="edge")
        self.assertNotEqual(router.primary_provider, "gemini")


# ===========================================================================
# 3. TTSRouter stream_audio (async)
# ===========================================================================

class TestTTSRouterStreamAudio(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.router = _build_router()
        self.mock_edge = MagicMock()
        self.mock_gemini = MagicMock()
        self.router._edge = self.mock_edge
        self.router._gemini = self.mock_gemini

    @staticmethod
    async def _gen(*chunks):
        for c in chunks:
            yield c

    @patch("backend.voice.output.tts_router.formatter")
    async def test_edge_primary_calls_edge_adapter(self, mock_fmt):
        mock_fmt.extract_emotion.return_value = "neutral"
        mock_fmt.format_text.return_value = "hello"
        self.router.primary_provider = "edge"
        self.mock_edge.generate_audio_stream = MagicMock(return_value=self._gen(b"audio"))
        chunks = [c async for c in self.router.stream_audio("hello", language="en")]
        self.mock_edge.generate_audio_stream.assert_called_once()
        self.assertEqual(chunks, [b"audio"])

    @patch("backend.voice.output.tts_router.formatter")
    async def test_gemini_success_skips_edge(self, mock_fmt):
        mock_fmt.extract_emotion.return_value = "neutral"
        mock_fmt.format_text.return_value = "hello"
        self.router.primary_provider = "gemini"
        self.mock_gemini.generate_audio_stream = MagicMock(return_value=self._gen(b"gemini"))
        self.mock_edge.generate_audio_stream = MagicMock(return_value=self._gen(b"edge"))
        chunks = [c async for c in self.router.stream_audio("hello", language="en")]
        self.mock_edge.generate_audio_stream.assert_not_called()
        self.assertIn(b"gemini", chunks)

    @patch("backend.voice.output.tts_router.formatter")
    async def test_gemini_exception_falls_back_to_edge(self, mock_fmt):
        mock_fmt.extract_emotion.return_value = "neutral"
        mock_fmt.format_text.return_value = "hello"
        self.router.primary_provider = "gemini"

        async def _fail():
            raise RuntimeError("timeout")
            yield

        self.mock_gemini.generate_audio_stream = MagicMock(return_value=_fail())
        self.mock_edge.generate_audio_stream = MagicMock(return_value=self._gen(b"fallback"))
        chunks = [c async for c in self.router.stream_audio("hello", language="en")]
        self.mock_edge.generate_audio_stream.assert_called_once()
        self.assertEqual(chunks, [b"fallback"])

    @patch("backend.voice.output.tts_router.formatter")
    async def test_gemini_zero_chunks_falls_back_to_edge(self, mock_fmt):
        mock_fmt.extract_emotion.return_value = "neutral"
        mock_fmt.format_text.return_value = "hello"
        self.router.primary_provider = "gemini"

        async def _empty():
            return
            yield

        self.mock_gemini.generate_audio_stream = MagicMock(return_value=_empty())
        self.mock_edge.generate_audio_stream = MagicMock(return_value=self._gen(b"fallback"))
        chunks = [c async for c in self.router.stream_audio("hello", language="en")]
        self.mock_edge.generate_audio_stream.assert_called_once()

    async def test_empty_string_yields_nothing(self):
        chunks = [c async for c in self.router.stream_audio("")]
        self.mock_edge.generate_audio_stream.assert_not_called()
        self.assertEqual(chunks, [])

    async def test_whitespace_only_yields_nothing(self):
        chunks = [c async for c in self.router.stream_audio("   ")]
        self.mock_edge.generate_audio_stream.assert_not_called()
        self.assertEqual(chunks, [])


# ===========================================================================
# 4. LRU embedding cache
# ===========================================================================

class TestEmbeddingLRUCache(unittest.TestCase):

    def setUp(self):
        _get_embedding_cached.cache_clear()

    def tearDown(self):
        _get_embedding_cached.cache_clear()

    @patch("backend.brain.memory.long_term_memory._get_embedding_uncached")
    def test_first_call_is_cache_miss(self, mock_uncached):
        mock_uncached.return_value = [0.1, 0.2, 0.3]
        _get_embedding("new text")
        mock_uncached.assert_called_once_with("new text")

    @patch("backend.brain.memory.long_term_memory._get_embedding_uncached")
    def test_second_same_text_is_cache_hit(self, mock_uncached):
        """Second call with same text must NOT hit the Gemini API."""
        mock_uncached.return_value = [0.1, 0.2, 0.3]
        _get_embedding("repeated")
        _get_embedding("repeated")
        mock_uncached.assert_called_once()

    @patch("backend.brain.memory.long_term_memory._get_embedding_uncached")
    def test_different_texts_each_miss(self, mock_uncached):
        mock_uncached.return_value = [1.0]
        _get_embedding("text a")
        _get_embedding("text b")
        self.assertEqual(mock_uncached.call_count, 2)

    @patch("backend.brain.memory.long_term_memory._get_embedding_uncached")
    def test_return_type_is_list_not_tuple(self, mock_uncached):
        """Cache stores tuples internally; public API must return list for numpy compat."""
        mock_uncached.return_value = [1.0, 2.0, 3.0]
        result = _get_embedding("type check")
        self.assertIsInstance(result, list)

    @patch("backend.brain.memory.long_term_memory._get_embedding_uncached")
    def test_none_api_response_returns_none(self, mock_uncached):
        mock_uncached.return_value = None
        self.assertIsNone(_get_embedding("offline"))

    @patch("backend.brain.memory.long_term_memory._get_embedding_uncached")
    def test_cache_info_tracks_hits_and_misses(self, mock_uncached):
        mock_uncached.return_value = [0.5]
        _get_embedding("track")
        _get_embedding("track")
        info = _get_embedding_cached.cache_info()
        self.assertEqual(info.misses, 1)
        self.assertEqual(info.hits, 1)

    def test_cache_maxsize_is_128(self):
        """Memory footprint contract: 128 * ~3KB = ~400KB max."""
        self.assertEqual(_get_embedding_cached.cache_info().maxsize, 128)


# ===========================================================================
# 5. Memory DB query structure + Python scoring
# ===========================================================================

class TestMemoryDBQuery(unittest.TestCase):

    def setUp(self):
        _get_embedding_cached.cache_clear()

    def tearDown(self):
        _get_embedding_cached.cache_clear()

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_limit_applied_to_query_chain(self, MockSL, _):
        mock_db = _mock_db_with_rows()
        MockSL.return_value = mock_db
        retrieve_relevant_memories("test")
        (mock_db.query.return_value
                .filter.return_value
                .order_by.return_value.limit
                .assert_called_once_with(_DB_LOAD_LIMIT))

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_filter_called_before_limit(self, MockSL, _):
        mock_db = _mock_db_with_rows()
        MockSL.return_value = mock_db
        retrieve_relevant_memories("test")
        mock_db.query.return_value.filter.assert_called_once()

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_db_close_always_called(self, MockSL, _):
        mock_db = _mock_db_with_rows()
        MockSL.return_value = mock_db
        retrieve_relevant_memories("test")
        mock_db.close.assert_called_once()

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_empty_db_returns_empty(self, MockSL, _):
        MockSL.return_value = _mock_db_with_rows()
        self.assertEqual(retrieve_relevant_memories("anything"), [])

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_importance_5_always_returned(self, MockSL, _):
        row = _FakeRow(content="critical memory", importance=5)
        MockSL.return_value = _mock_db_with_rows(row)
        self.assertIn("critical memory", retrieve_relevant_memories(""))

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_low_importance_no_keyword_excluded(self, MockSL, _):
        row = _FakeRow(content="unrelated xyz content", importance=3)
        MockSL.return_value = _mock_db_with_rows(row)
        self.assertEqual(retrieve_relevant_memories("completely different"), [])

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_keyword_match_returns_memory(self, MockSL, _):
        row = _FakeRow(content="user loves python programming", importance=3)
        MockSL.return_value = _mock_db_with_rows(row)
        result = retrieve_relevant_memories("python programming")
        self.assertIn("user loves python programming", result)

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_category_filter_excludes_low_importance_wrong_category(self, MockSL, _):
        row = _FakeRow(content="general fact", importance=3, category="general")
        MockSL.return_value = _mock_db_with_rows(row)
        self.assertEqual(retrieve_relevant_memories("", active_category="personal"), [])

    @patch("backend.brain.memory.long_term_memory._get_embedding", return_value=None)
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_importance_4_bypasses_category_filter(self, MockSL, _):
        row = _FakeRow(content="high priority fact", importance=4, category="general")
        MockSL.return_value = _mock_db_with_rows(row)
        self.assertIn("high priority fact",
                      retrieve_relevant_memories("", active_category="personal"))

    @patch("backend.brain.memory.long_term_memory._get_embedding")
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_identical_vector_sim_1_included(self, MockSL, mock_embed):
        vector = [1.0, 0.0, 0.0]
        mock_embed.return_value = vector
        row = _FakeRow(content="vector match", importance=3, vector=json.dumps(vector))
        MockSL.return_value = _mock_db_with_rows(row)
        self.assertIn("vector match", retrieve_relevant_memories("query"))

    @patch("backend.brain.memory.long_term_memory._get_embedding")
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_orthogonal_vector_sim_0_excluded(self, MockSL, mock_embed):
        mock_embed.return_value = [1.0, 0.0, 0.0]
        row = _FakeRow(content="no match", importance=3,
                       vector=json.dumps([0.0, 1.0, 0.0]))
        MockSL.return_value = _mock_db_with_rows(row)
        self.assertEqual(retrieve_relevant_memories("query"), [])

    @patch("backend.brain.memory.long_term_memory._get_embedding")
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_nan_vector_does_not_crash(self, MockSL, mock_embed):
        mock_embed.return_value = [1.0, 0.0, 0.0]
        row = _FakeRow(content="nan vector", importance=3,
                       vector=json.dumps([float("nan"), float("inf"), 2.0]))
        MockSL.return_value = _mock_db_with_rows(row)
        try:
            retrieve_relevant_memories("query")
        except Exception as exc:
            self.fail(f"Raised unexpectedly: {exc}")

    @patch("backend.brain.memory.long_term_memory._get_embedding")
    @patch("backend.brain.memory.long_term_memory.SessionLocal")
    def test_malformed_vector_json_does_not_crash(self, MockSL, mock_embed):
        mock_embed.return_value = [1.0, 0.0, 0.0]
        row = _FakeRow(content="bad json", importance=3, vector="{{invalid}}")
        MockSL.return_value = _mock_db_with_rows(row)
        try:
            retrieve_relevant_memories("query")
        except Exception as exc:
            self.fail(f"Raised unexpectedly: {exc}")


# ===========================================================================
# 6. _DB_LOAD_LIMIT sanity
# ===========================================================================

class TestDBLoadLimitSanity(unittest.TestCase):

    def test_is_positive_integer(self):
        self.assertIsInstance(_DB_LOAD_LIMIT, int)
        self.assertGreater(_DB_LOAD_LIMIT, 0)

    def test_under_ten_thousand(self):
        """Unbounded limit defeats the purpose of the fix."""
        self.assertLess(_DB_LOAD_LIMIT, 10_000)

    def test_at_least_fifty(self):
        """Too small starves the scorer of candidates."""
        self.assertGreaterEqual(_DB_LOAD_LIMIT, 50)


if __name__ == "__main__":
    unittest.main()
