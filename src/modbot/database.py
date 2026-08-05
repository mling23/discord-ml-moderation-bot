"""Async SQLite persistence layer.

Two notable improvements over the original:

* All access is async (via ``aiosqlite``) so database calls never block the
  Discord gateway event loop.
* Spam vectors are stored with ``numpy.save`` instead of ``pickle``. Pickle can
  execute arbitrary code when loading untrusted data (OWASP A08); ``numpy.save``
  with ``allow_pickle=False`` is a safe, purpose-built format for arrays.
"""

import io
from collections.abc import Iterable
from datetime import datetime, timezone

import aiosqlite
import numpy as np


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_vector(vector: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, vector.astype(np.float32), allow_pickle=False)
    return buffer.getvalue()


def _deserialize_vector(blob: bytes) -> np.ndarray:
    buffer = io.BytesIO(blob)
    return np.load(buffer, allow_pickle=False)


class DatabaseManager:
    def __init__(self, db_path: str = "moderation.db"):
        self.db_path = db_path

    async def init_db(self) -> None:
        """Create the required tables if they do not exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    joined_at TEXT,
                    message_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending'
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS spam_vectors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    embedding BLOB,
                    original_text TEXT,
                    content_hash TEXT UNIQUE,
                    added_at TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    content TEXT,
                    content_hash TEXT,
                    spam_score REAL,
                    action TEXT,
                    timestamp TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            await db.commit()

    # --- Users (only unvetted users are tracked in detail) ---
    async def add_pending_user(self, user_id: int, joined_at=None) -> None:
        join_str = joined_at.isoformat() if joined_at else _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, joined_at) VALUES (?, ?)",
                (user_id, join_str),
            )
            await db.commit()

    async def get_user(self, user_id: int) -> tuple[str, int] | None:
        """Return (status, message_count) for a user, or None if unknown."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status, message_count FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                return await cursor.fetchone()

    async def increment_message_count(self, user_id: int) -> int:
        """Add one clean message to a user's tally and return the new total."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET message_count = message_count + 1 WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()
            async with db.execute(
                "SELECT message_count FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else 0

    async def set_trusted(self, user_id: int) -> None:
        """Promote a user to trusted and drop their personal join data."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO users (user_id, status, joined_at) VALUES (?, 'trusted', NULL) "
                "ON CONFLICT(user_id) DO UPDATE SET status = 'trusted', joined_at = NULL",
                (user_id,),
            )
            await db.commit()

    async def trust_members(self, user_ids: Iterable[int]) -> None:
        """Bulk-mark existing members as trusted (used to seed at first launch)."""
        rows = [(uid,) for uid in user_ids]
        if not rows:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT INTO users (user_id, status) VALUES (?, 'trusted') "
                "ON CONFLICT(user_id) DO UPDATE SET status = 'trusted'",
                rows,
            )
            await db.commit()

    # --- One-time seed flag ---
    async def is_seeded(self) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM meta WHERE key = 'seeded'"
            ) as cursor:
                return await cursor.fetchone() is not None

    async def mark_seeded(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('seeded', '1')"
            )
            await db.commit()

    # --- Spam vectors (deduped by content hash) ---
    async def add_spam_vector(
        self, embedding: np.ndarray, text: str, content_hash: str
    ) -> bool:
        """Store a learned spam signature. Returns False if it was a duplicate."""
        blob = _serialize_vector(embedding)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO spam_vectors "
                "(embedding, original_text, content_hash, added_at) VALUES (?, ?, ?, ?)",
                (blob, text, content_hash, _now_iso()),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def load_vectors(self) -> list[np.ndarray]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT embedding FROM spam_vectors") as cursor:
                rows = await cursor.fetchall()
        return [_deserialize_vector(row[0]) for row in rows]

    # --- Audit log ---
    async def log_action(
        self,
        user_id: int,
        content: str,
        content_hash: str | None,
        score: float,
        action: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO logs (user_id, content, content_hash, spam_score, action, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, content, content_hash, score, action, _now_iso()),
            )
            await db.commit()
