"""The headline test: memory is durable storage, not a process-local dict.

The brief's #1 signal is "two sequential calls with the same user_id prove it — no
in-memory dict tricks." We prove it the hard way: write with one engine, dispose it
completely, then read back through a *brand-new* engine and connection pool pointed
at the same file. An in-memory dict cannot survive that.
"""

import os

import pytest

from app.db.session import Database
from app.memory.sql_store import SqlMemoryStore


@pytest.fixture
def db_url(tmp_path: object) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/persist_test.db"  # type: ignore[operator]


async def test_memory_survives_a_brand_new_engine(db_url: str) -> None:
    # --- "Request 1": write, commit, then tear the engine down entirely ---
    db1 = Database(db_url)
    await db1.create_all()
    async with db1.sessionmaker() as s1:
        store1 = SqlMemoryStore(s1)
        await store1.append_message(
            user_id="acme", session_id="sess-1", role="user",
            content="What's your enterprise pricing?",
        )
        await store1.append_message(
            user_id="acme", session_id="sess-1", role="assistant",
            content="Enterprise is $499/mo.", tools_called=["search_catalog"],
        )
        await s1.commit()
    await db1.dispose()

    # --- "Request 2": a separate engine over the SAME file reads it back ---
    db2 = Database(db_url)
    async with db2.sessionmaker() as s2:
        history = await SqlMemoryStore(s2).get_history("acme")
    await db2.dispose()

    assert [t.content for t in history] == [
        "What's your enterprise pricing?",
        "Enterprise is $499/mo.",
    ]
    assert history[1].tools_called == ["search_catalog"]
    assert history[1].session_id == "sess-1"
    # And it physically lives on disk:
    assert os.path.getsize(db_url.replace("sqlite+aiosqlite:///", "")) > 0


async def test_recent_turns_are_oldest_first_and_bounded(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    async with db.sessionmaker() as s:
        store = SqlMemoryStore(s)
        for i in range(5):
            await store.append_message(
                user_id="u", session_id="s", role="user", content=f"msg-{i}"
            )
        await s.commit()
        recent = await store.get_recent_turns("u", limit=3)
    await db.dispose()

    assert [t.content for t in recent] == ["msg-2", "msg-3", "msg-4"]


async def test_summary_state_roundtrips_and_upserts(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    async with db.sessionmaker() as s:
        store = SqlMemoryStore(s)
        assert await store.get_summary_state("u") is None
        await store.upsert_summary(user_id="u", summary="liked Enterprise", up_to_seq=4)
        await store.upsert_summary(user_id="u", summary="now wants SSO + SLA", up_to_seq=8)
        await s.commit()
        state = await store.get_summary_state("u")
    await db.dispose()

    assert state is not None
    assert state.summary == "now wants SSO + SLA"
    assert state.up_to_seq == 8


async def test_wipe_user_is_a_scoped_gdpr_reset(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    async with db.sessionmaker() as s:
        store = SqlMemoryStore(s)
        await store.append_message(user_id="u1", session_id="a", role="user", content="hi")
        await store.append_message(user_id="u2", session_id="b", role="user", content="hello")
        await store.upsert_summary(user_id="u1", summary="x", up_to_seq=1)
        await s.commit()

        deleted = await store.wipe_user("u1")
        await s.commit()
    await db.dispose()

    assert deleted == 2  # one message + one summary


async def test_wipe_only_touches_target_user(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    async with db.sessionmaker() as s:
        store = SqlMemoryStore(s)
        await store.append_message(user_id="u1", session_id="a", role="user", content="hi")
        await store.append_message(user_id="u2", session_id="b", role="user", content="hello")
        await s.commit()
        await store.wipe_user("u1")
        await s.commit()
        assert await store.count_turns("u1") == 0
        assert await store.count_turns("u2") == 1
    await db.dispose()
