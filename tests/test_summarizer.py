"""Memory summarization (bonus): fold old turns, keep the recent window, advance up_to_seq."""

import pytest

from app.db.session import Database
from app.memory.sql_store import SqlMemoryStore
from app.memory.summarizer import Summarizer
from tests.support import ScriptedLLM, final_text


@pytest.fixture
def db_url(tmp_path: object) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/sum.db"  # type: ignore[operator]


async def _seed(memory: SqlMemoryStore, n: int, start: int = 0) -> None:
    for i in range(start, start + n):
        await memory.append_message(user_id="u", session_id="x", role="user", content=f"q{i}")


async def test_folds_old_turns_and_keeps_recent_window(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    async with db.sessionmaker() as session:
        memory = SqlMemoryStore(session)
        await _seed(memory, 6)
        await session.commit()
        summarizer = Summarizer(
            ScriptedLLM([final_text("Summary: asked q0..q3")]),
            model="m", max_tokens=128, recent_window=2, summarize_after=3,
        )
        changed = await summarizer.run(memory, "u")
        await session.commit()
        state = await memory.get_summary_state("u")
    await db.dispose()

    assert changed is True
    assert state is not None
    assert "Summary" in state.summary
    assert state.up_to_seq == 4  # folded seq 1-4, left the last 2 turns verbatim


async def test_noop_below_threshold(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    async with db.sessionmaker() as session:
        memory = SqlMemoryStore(session)
        await _seed(memory, 2)
        await session.commit()
        summarizer = Summarizer(
            ScriptedLLM([final_text("unused")]),
            model="m", max_tokens=128, recent_window=2, summarize_after=3,
        )
        changed = await summarizer.run(memory, "u")
    await db.dispose()
    assert changed is False


async def test_incremental_fold_advances_up_to_seq(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    async with db.sessionmaker() as session:
        memory = SqlMemoryStore(session)
        await _seed(memory, 6)
        await session.commit()
        summarizer = Summarizer(
            ScriptedLLM([final_text("s1"), final_text("s2")]),
            model="m", max_tokens=128, recent_window=2, summarize_after=3,
        )
        await summarizer.run(memory, "u")
        await session.commit()

        await _seed(memory, 4, start=6)  # now 10 turns total
        await session.commit()
        await summarizer.run(memory, "u")
        await session.commit()
        state = await memory.get_summary_state("u")
    await db.dispose()

    assert state is not None
    assert state.up_to_seq == 8  # second fold advanced past the first
