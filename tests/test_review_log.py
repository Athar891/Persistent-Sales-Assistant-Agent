"""flag_for_human writes a real human_review_log row that the reviewer endpoint can query."""

import pytest

from app.db.session import Database
from app.db.unit_of_work import SqlUnitOfWork
from app.models.eval import EvalBlock
from app.reviews.notifier import NullNotifier
from app.reviews.sql_review_log import SqlReviewLog
from app.tools.flag_for_human import FlagForHumanTool


@pytest.fixture
def db_url(tmp_path: object) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/rev.db"  # type: ignore[operator]


async def test_model_initiated_flag_records_a_row_without_scores(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    tool = FlagForHumanTool(
        SqlUnitOfWork(db.sessionmaker), NullNotifier(), user_id="u", session_id="sess"
    )
    out = await tool.run({"reason": "asked about something off-catalog"})

    async with db.sessionmaker() as session:
        entries = await SqlReviewLog(session).list_entries(user_id="u")
    await db.dispose()

    assert "Escalated" in out
    assert len(entries) == 1
    assert entries[0].confidence is None  # no eval existed yet
    assert entries[0].reason.startswith("Model-initiated:")
    assert entries[0].resolved is False


async def test_threshold_escalation_stores_the_eval_scores(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    tool = FlagForHumanTool(
        SqlUnitOfWork(db.sessionmaker), NullNotifier(), user_id="u", session_id="sess"
    )
    evaluation = EvalBlock(
        groundedness=0.3, relevance=0.4, confidence=0.5, flagged=True, reasoning="weak"
    )
    await tool.escalate(reason="Low confidence", evaluation=evaluation, message_id=42)

    async with db.sessionmaker() as session:
        entries = await SqlReviewLog(session).list_entries()
    await db.dispose()

    assert entries[0].confidence == 0.5
    assert entries[0].message_id == 42


async def test_list_filters_by_user_and_unresolved(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    async with db.sessionmaker() as session:
        reviews = SqlReviewLog(session)
        await reviews.record(user_id="a", session_id="s", reason="r1")
        await reviews.record(user_id="b", session_id="s", reason="r2")
        await session.commit()
        only_a = await reviews.list_entries(user_id="a")
        unresolved = await reviews.list_entries(only_unresolved=True)
    await db.dispose()

    assert [e.user_id for e in only_a] == ["a"]
    assert len(unresolved) == 2  # nothing resolved yet
