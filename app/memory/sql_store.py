"""SqlMemoryStore — the default MemoryPort adapter.

Backed by async SQLAlchemy, so the *same* code runs on SQLite locally and Postgres
in production. The store is request-scoped: it borrows the request's session and
never commits on its own (the session dependency owns the transaction boundary),
which keeps a /chat request's memory writes and eval write atomic.
"""

from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Eval, HumanReviewLog, MemorySummary, Message
from app.domain.types import SummaryState, Turn


def _to_turn(m: Message) -> Turn:
    return Turn(
        role=m.role,
        content=m.content,
        session_id=m.session_id,
        tools_called=m.tools_called,
        created_at=m.created_at,
        seq=m.id,
    )


class SqlMemoryStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append_message(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        tools_called: list[str] | None = None,
    ) -> Turn:
        msg = Message(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            tools_called=tools_called,
        )
        self._session.add(msg)
        await self._session.flush()  # assigns msg.id without ending the transaction
        return _to_turn(msg)

    async def get_history(self, user_id: str) -> list[Turn]:
        rows = await self._session.scalars(
            select(Message).where(Message.user_id == user_id).order_by(Message.id.asc())
        )
        return [_to_turn(m) for m in rows]

    async def get_recent_turns(self, user_id: str, limit: int) -> list[Turn]:
        rows = await self._session.scalars(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        turns = [_to_turn(m) for m in rows]
        turns.reverse()  # hand them back oldest-first
        return turns

    async def count_turns(self, user_id: str) -> int:
        count = await self._session.scalar(
            select(func.count()).select_from(Message).where(Message.user_id == user_id)
        )
        return int(count or 0)

    async def get_summary_state(self, user_id: str) -> SummaryState | None:
        row = await self._session.scalar(
            select(MemorySummary).where(MemorySummary.user_id == user_id)
        )
        if row is None:
            return None
        return SummaryState(summary=row.summary, up_to_seq=row.up_to_seq)

    async def upsert_summary(self, *, user_id: str, summary: str, up_to_seq: int) -> None:
        row = await self._session.scalar(
            select(MemorySummary).where(MemorySummary.user_id == user_id)
        )
        if row is None:
            self._session.add(
                MemorySummary(user_id=user_id, summary=summary, up_to_seq=up_to_seq)
            )
        else:
            row.summary = summary
            row.up_to_seq = up_to_seq
        await self._session.flush()

    async def wipe_user(self, user_id: str) -> int:
        """GDPR reset: remove every row tied to the user, return the count deleted."""
        total = 0
        for stmt in (
            delete(Eval).where(Eval.user_id == user_id),
            delete(HumanReviewLog).where(HumanReviewLog.user_id == user_id),
            delete(MemorySummary).where(MemorySummary.user_id == user_id),
            delete(Message).where(Message.user_id == user_id),
        ):
            result = cast("CursorResult[Any]", await self._session.execute(stmt))
            total += result.rowcount or 0
        await self._session.flush()
        return total
