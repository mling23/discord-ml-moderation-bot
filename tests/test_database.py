"""Database tests.

These require ``aiosqlite`` (a runtime dependency). CI installs only the
lightweight test deps, so this module is skipped there; it runs for developers
who have installed the full stack with ``pip install -e ".[dev]"``.
"""

import numpy as np
import pytest

pytest.importorskip("aiosqlite")
import pytest_asyncio  # noqa: E402

from modbot.database import DatabaseManager  # noqa: E402


@pytest_asyncio.fixture
async def db(tmp_path):
    manager = DatabaseManager(str(tmp_path / "test.db"))
    await manager.init_db()
    return manager


async def test_new_user_starts_pending(db):
    await db.add_pending_user(1)
    assert await db.get_user(1) == ("pending", 0)


async def test_unknown_user_is_none(db):
    assert await db.get_user(999) is None


async def test_message_count_increments(db):
    await db.add_pending_user(1)
    assert await db.increment_message_count(1) == 1
    assert await db.increment_message_count(1) == 2


async def test_set_trusted(db):
    await db.add_pending_user(1)
    await db.set_trusted(1)
    status, _count = await db.get_user(1)
    assert status == "trusted"


async def test_trust_members_bulk_seed(db):
    await db.trust_members([10, 11, 12])
    assert (await db.get_user(11))[0] == "trusted"


async def test_seeded_flag(db):
    assert await db.is_seeded() is False
    await db.mark_seeded()
    assert await db.is_seeded() is True


async def test_spam_vector_dedup(db):
    vector = np.ones(4, dtype=np.float32)
    assert await db.add_spam_vector(vector, "buy now", "hash1") is True
    assert await db.add_spam_vector(vector, "buy now", "hash1") is False
    assert len(await db.load_vectors()) == 1


async def test_user_status_counts(db):
    await db.add_pending_user(1)
    await db.add_pending_user(2)
    await db.set_trusted(2)
    await db.trust_members([10, 11])
    trusted, pending = await db.get_user_status_counts()
    assert trusted == 3
    assert pending == 1


async def test_reset_data_clears_all_runtime_tables(db):
    await db.add_pending_user(1)
    await db.set_trusted(2)
    await db.log_action(1, "spam", "hash1", 10, "deleted")
    vector = np.ones(4, dtype=np.float32)
    await db.add_spam_vector(vector, "buy now", "hash1")
    await db.mark_seeded()

    summary = await db.reset_data()

    assert summary["users"] == 2
    assert summary["spam_vectors"] == 1
    assert summary["logs"] == 1
    assert await db.get_user(1) is None
    assert await db.get_user(2) is None
    assert len(await db.load_vectors()) == 0
    assert await db.is_seeded() is False


async def test_load_vector_records_includes_ids_and_text(db):
    vector = np.ones(4, dtype=np.float32)
    await db.add_spam_vector(vector, "buy now", "hash1")
    records = await db.load_vector_records()
    assert len(records) == 1
    assert records[0]["id"] >= 1
    assert records[0]["text"] == "buy now"
    assert records[0]["vector"].shape[0] == 4


async def test_template_hit_tracking_and_ranking(db):
    v1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
    await db.add_spam_vector(v1, "template one", "h1")
    await db.add_spam_vector(v2, "template two", "h2")
    records = await db.load_vector_records()
    id1 = records[0]["id"]
    id2 = records[1]["id"]

    await db.increment_spam_vector_hit(id1, 0.91, "match a")
    await db.increment_spam_vector_hit(id1, 0.93, "match b")
    await db.increment_spam_vector_hit(id2, 0.89, "match c")

    top = await db.top_spam_vector_hits(limit=5)
    assert top[0]["vector_id"] == id1
    assert top[0]["hit_count"] == 2
    assert top[0]["last_similarity"] == pytest.approx(0.93)
    assert top[1]["vector_id"] == id2
    assert top[1]["hit_count"] == 1
