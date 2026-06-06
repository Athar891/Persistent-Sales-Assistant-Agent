"""SqlReviewLog — the default ReviewLogPort adapter.

Persists every escalation so the human-reviewer endpoint is a real query, and the
`/evals` aggregation and review workflow read from the same database as everything else.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HumanReviewLog
from app.domain.types import ReviewEntry
from app.models.eval import EvalBlock


def _to_entry(row: HumanReviewLog) -> ReviewEntry:
    return ReviewEntry(
        id=row.id,
        user_id=row.user_id,
        session_id=row.session_id,
        message_id=row.message_id,
        reason=row.reason,
        groundedness=row.groundedness,
        relevance=row.relevance,
        confidence=row.confidence,
        resolved=row.resolved,
        created_at=row.created_at,
    )


class SqlReviewLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        user_id: str,
        session_id: str,
        reason: str,
        evaluation: EvalBlock | None = None,
        message_id: int | None = None,
    ) -> None:
        self._session.add(
            HumanReviewLog(
                user_id=user_id,
                session_id=session_id,
                message_id=message_id,
                reason=reason,
                groundedness=evaluation.groundedness if evaluation else None,
                relevance=evaluation.relevance if evaluation else None,
                confidence=evaluation.confidence if evaluation else None,
            )
        )
        await self._session.flush()

    async def list_entries(
        self, *, user_id: str | None = None, only_unresolved: bool = False, limit: int = 100
    ) -> list[ReviewEntry]:
        stmt = select(HumanReviewLog)
        if user_id is not None:
            stmt = stmt.where(HumanReviewLog.user_id == user_id)
        if only_unresolved:
            stmt = stmt.where(HumanReviewLog.resolved.is_(False))
        stmt = stmt.order_by(HumanReviewLog.id.desc()).limit(limit)
        rows = await self._session.scalars(stmt)
        return [_to_entry(r) for r in rows]
