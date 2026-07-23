import sqlite3
import os
import json
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
import asyncio

from backend.config.runtime_paths import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = str(DATA_DIR / "metrics.db")

@dataclass
class RequestMetrics:
    timestamp: str          # ISO format
    session_id: str
    intent_class: str       # workflow / standard / fast_path
    tokens_input: int
    tokens_output: int
    latency_ms: int
    model_used: str
    model_version: str
    model_tier: str         # fast / reasoning / thinking (actual tier used)
    tool_calls: list[str]
    verifier_retries: int   # how many ResultVerifier retries occurred
    fast_path_hit: bool     # True when Intent Sentinel or direct-OS path short-circuited
    error: str | None

class Observability:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS request_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        session_id TEXT,
                        intent_class TEXT,
                        tokens_input INTEGER,
                        tokens_output INTEGER,
                        latency_ms INTEGER,
                        model_used TEXT,
                        model_version TEXT,
                        model_tier TEXT DEFAULT 'fast',
                        tool_calls TEXT,
                        verifier_retries INTEGER DEFAULT 0,
                        fast_path_hit BOOLEAN DEFAULT 0,
                        error TEXT
                    )
                """)
                # Migrate existing DBs: add model_tier column if missing
                try:
                    conn.execute("ALTER TABLE request_metrics ADD COLUMN model_tier TEXT DEFAULT 'fast'")
                except sqlite3.OperationalError:
                    pass  # Column already exists
        except Exception as e:
            logger.error(f"Failed to init metrics.db: {e}")

    async def log(self, metrics: RequestMetrics):
        """Asynchronously log metrics to DB to avoid blocking."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._log_sync, metrics)

    def _log_sync(self, metrics: RequestMetrics):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO request_metrics (
                        timestamp, session_id, intent_class, tokens_input, tokens_output,
                        latency_ms, model_used, model_version, model_tier, tool_calls,
                        verifier_retries, fast_path_hit, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metrics.timestamp,
                    metrics.session_id,
                    metrics.intent_class,
                    metrics.tokens_input,
                    metrics.tokens_output,
                    metrics.latency_ms,
                    metrics.model_used,
                    metrics.model_version,
                    getattr(metrics, 'model_tier', 'fast'),
                    json.dumps(metrics.tool_calls),
                    metrics.verifier_retries,
                    metrics.fast_path_hit,
                    metrics.error
                ))
        except Exception as e:
            logger.error(f"Failed to insert into metrics.db: {e}")

    def get_session_stats(self, session_id: str) -> dict:
        """Return aggregated stats for a session — used by BudgetManager and future dashboard."""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute("""
                    SELECT
                        COUNT(*) as requests,
                        SUM(tokens_input + tokens_output) as total_tokens,
                        AVG(latency_ms) as avg_latency_ms,
                        SUM(verifier_retries) as total_retries,
                        SUM(fast_path_hit) as fast_path_hits
                    FROM request_metrics
                    WHERE session_id = ?
                """, (session_id,)).fetchone()
                if row:
                    return {
                        "requests": row[0] or 0,
                        "total_tokens": row[1] or 0,
                        "avg_latency_ms": round(row[2] or 0, 1),
                        "total_retries": row[3] or 0,
                        "fast_path_hits": row[4] or 0,
                    }
        except Exception as e:
            logger.error(f"Failed to query session stats: {e}")
        return {}

    def get_recent_errors(self, limit: int = 20) -> list[dict]:
        """Return the most recent errored requests — useful for debugging."""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                rows = conn.execute("""
                    SELECT timestamp, session_id, intent_class, error
                    FROM request_metrics
                    WHERE error IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                return [
                    {"timestamp": r[0], "session_id": r[1],
                     "intent_class": r[2], "error": r[3]}
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Failed to query recent errors: {e}")
            return []

observability = Observability()
