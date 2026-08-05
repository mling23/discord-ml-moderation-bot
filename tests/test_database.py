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
