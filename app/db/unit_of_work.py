"""SqlUnitOfWork — the default UnitOfWork adapter.

Hands out the SQL-backed repositories bound to a fresh, short-lived session, and owns
its transaction boundary: commit on success, roll back on error, and — because the
session closes when the block exits — the pooled connection goes straight back to the
pool. That is the whole point: a /chat turn opens several of these in quick succession
instead of holding one connection open across every (slow) LLM call.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ports import Repositories
from app.evals.sql_eval_store import SqlEvalStore
from app.memory.sql_store import SqlMemoryStore
from app.reviews.sql_review_log import SqlReviewLog


class SqlUnitOfWork:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[Repositories]:
        async with self._sessionmaker() as session:
            try:
                yield Repositories(
                    memory=SqlMemoryStore(session),
                    evals=SqlEvalStore(session),
                    reviews=SqlReviewLog(session),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
