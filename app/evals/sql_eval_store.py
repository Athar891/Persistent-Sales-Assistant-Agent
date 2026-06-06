"""SqlEvalStore — the default EvalStorePort.

Persists every eval so GET /chat/{user_id}/evals is a real aggregation query, not a
recompute. Aggregation is done in SQL (counts + averages), so it stays cheap as history grows.
"""

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Eval
from app.domain.types import EvalAggregate
from app.models.eval import EvalBlock


class SqlEvalStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self, *, message_id: int, user_id: str, session_id: str, evaluation: EvalBlock
    ) -> None:
        self._session.add(
            Eval(
                message_id=message_id,
                user_id=user_id,
                session_id=session_id,
                groundedness=evaluation.groundedness,
                relevance=evaluation.relevance,
                confidence=evaluation.confidence,
                flagged=evaluation.flagged,
                reasoning=evaluation.reasoning,
            )
        )
        await self._session.flush()

    async def aggregate(self, user_id: str, *, high_confidence_threshold: float) -> EvalAggregate:
        high_conf = case((Eval.confidence >= high_confidence_threshold, 1), else_=0)
        flagged = case((Eval.flagged.is_(True), 1), else_=0)
        stmt = (
            select(
                func.count(Eval.id),
                func.coalesce(func.avg(Eval.groundedness), 0.0),
                func.coalesce(func.avg(Eval.relevance), 0.0),
                func.coalesce(func.avg(Eval.confidence), 0.0),
                func.coalesce(func.sum(high_conf), 0),
                func.coalesce(func.sum(flagged), 0),
            )
            .where(Eval.user_id == user_id)
        )
        row = (await self._session.execute(stmt)).one()
        total = int(row[0])
        high = int(row[4])
        return EvalAggregate(
            total=total,
            flagged=int(row[5]),
            high_confidence=high,
            high_confidence_pct=round(high / total * 100.0, 1) if total else 0.0,
            avg_groundedness=round(float(row[1]), 3),
            avg_relevance=round(float(row[2]), 3),
            avg_confidence=round(float(row[3]), 3),
        )
