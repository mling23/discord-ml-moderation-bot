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

    async def get_user_status_counts(self) -> tuple[int, int]:
        """Return ``(trusted_count, pending_count)`` from the users table."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status, COUNT(*) FROM users GROUP BY status"
            ) as cursor:
                rows = await cursor.fetchall()
        counts = {status: count for status, count in rows}
        return int(counts.get("trusted", 0)), int(counts.get("pending", 0))

    async def get_runtime_counts(self) -> dict[str, int]:
        """Return high-level row counts for admin diagnostics."""
        trusted, pending = await self.get_user_status_counts()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM spam_vectors") as cursor:
                spam_vectors = int((await cursor.fetchone())[0])
            async with db.execute("SELECT COUNT(*) FROM logs") as cursor:
                logs = int((await cursor.fetchone())[0])
        return {
            "trusted": trusted,
            "pending": pending,
            "spam_vectors": spam_vectors,
            "logs": logs,
        }

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

    async def reset_data(self) -> dict[str, int]:
        """Delete all runtime data and return a summary of removed rows.

        This clears users, learned spam vectors, logs, and meta flags so the bot
        can be reseeded cleanly.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                users_count = int((await cursor.fetchone())[0])
            async with db.execute("SELECT COUNT(*) FROM spam_vectors") as cursor:
                vectors_count = int((await cursor.fetchone())[0])
            async with db.execute("SELECT COUNT(*) FROM logs") as cursor:
                logs_count = int((await cursor.fetchone())[0])

            await db.execute("DELETE FROM users")
            await db.execute("DELETE FROM spam_vectors")
            await db.execute("DELETE FROM logs")
            await db.execute("DELETE FROM meta")
            await db.commit()

        return {
            "users": users_count,
            "spam_vectors": vectors_count,
            "logs": logs_count,
        }

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

    async def load_vector_records(self) -> list[dict]:
        """Load vectors with ids/text for in-memory nearest-match context."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, embedding, original_text FROM spam_vectors ORDER BY id"
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {
                "id": int(row[0]),
                "vector": _deserialize_vector(row[1]),
                "text": row[2] or "",
            }
            for row in rows
        ]

    async def increment_spam_vector_hit(
        self, vector_id: int, similarity: float, matched_text: str
    ) -> None:
        """Increment hit stats for a template and store a sample matched text."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS spam_vector_hits (
                    vector_id INTEGER PRIMARY KEY,
                    hit_count INTEGER DEFAULT 0,
                    last_similarity REAL,
                    last_matched_text TEXT,
                    last_hit_at TEXT
                )
                """
            )
            await db.execute(
                "INSERT INTO spam_vector_hits "
                "(vector_id, hit_count, last_similarity, last_matched_text, last_hit_at) "
                "VALUES (?, 1, ?, ?, ?) "
                "ON CONFLICT(vector_id) DO UPDATE SET "
                "hit_count = hit_count + 1, "
                "last_similarity = excluded.last_similarity, "
                "last_matched_text = excluded.last_matched_text, "
                "last_hit_at = excluded.last_hit_at",
                (vector_id, similarity, matched_text[:1000], _now_iso()),
            )
            await db.commit()

    async def top_spam_vector_hits(self, limit: int = 10) -> list[dict]:
        """Return top templates by cosine-match hit count."""
        safe_limit = max(1, min(limit, 25))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS spam_vector_hits (
                    vector_id INTEGER PRIMARY KEY,
                    hit_count INTEGER DEFAULT 0,
                    last_similarity REAL,
                    last_matched_text TEXT,
                    last_hit_at TEXT
                )
                """
            )
            async with db.execute(
                "SELECT h.vector_id, h.hit_count, h.last_similarity, h.last_hit_at, "
                "s.original_text "
                "FROM spam_vector_hits h "
                "LEFT JOIN spam_vectors s ON s.id = h.vector_id "
                "ORDER BY h.hit_count DESC, h.last_hit_at DESC "
                "LIMIT ?",
                (safe_limit,),
            ) as cursor:
                rows = await cursor.fetchall()

        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "vector_id": int(row[0]),
                    "hit_count": int(row[1]),
                    "last_similarity": float(row[2]) if row[2] is not None else 0.0,
                    "last_hit_at": row[3] or "",
                    "template_text": (row[4] or "")[:120],
                }
            )
        return out

    async def list_spam_vector_previews(self, limit: int = 5) -> list[dict]:
        """Return lightweight previews for recent learned spam vectors."""
        safe_limit = max(1, min(limit, 25))
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, content_hash, original_text, added_at "
                "FROM spam_vectors ORDER BY id DESC LIMIT ?",
                (safe_limit,),
            ) as cursor:
                rows = await cursor.fetchall()

        previews: list[dict] = []
        for row in rows:
            text = (row[2] or "").replace("\n", " ").strip()
            previews.append(
                {
                    "id": int(row[0]),
                    "hash": row[1] or "",
                    "text_preview": text[:80],
                    "added_at": row[3] or "",
                }
            )
        return previews

    async def get_spam_vector_details(self, vector_id: int) -> dict | None:
        """Return detailed metadata/stats for a specific spam vector row."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, embedding, content_hash, original_text, added_at "
                "FROM spam_vectors WHERE id = ?",
                (vector_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None

        vector = _deserialize_vector(row[1])
        preview_values = ", ".join(f"{float(v):.4f}" for v in vector[:8])
        return {
            "id": int(row[0]),
            "hash": row[2] or "",
            "text": row[3] or "",
            "added_at": row[4] or "",
            "dimension": int(vector.shape[0]),
            "norm": float(np.linalg.norm(vector)),
            "values_preview": preview_values,
        }

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
