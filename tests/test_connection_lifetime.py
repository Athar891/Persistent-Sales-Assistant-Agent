"""Regression test for the #4 fix: a /chat turn must not hold a pooled DB connection while
it waits on the LLM.

We wrap the LLM so that, at the instant the model is invoked, it records how many
connections are currently checked out of the engine's pool. With the old single-request
transaction this was always 1 (held idle across every call); the UnitOfWork refactor must
keep it at 0 for every agent, evaluator and summarizer call.
"""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.catalog.keyword_search import KeywordCatalogSearch
from app.db.session import Database
from app.db.unit_of_work import SqlUnitOfWork
from app.domain.types import LLMReply
from app.reviews.notifier import NullNotifier
from app.services.chat_service import ChatService
from app.services.eval_service import LLMEvaluator
from app.settings import Settings
from tests.support import StubLLM

CATALOG = str(Path(__file__).resolve().parents[1] / "catalog.json")


class _PoolProbeLLM(StubLLM):
    """Drives the agent like StubLLM, but samples pool checkouts on every model call."""

    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__()
        self._engine = engine
        self.checkouts: list[int] = []

    async def create_message(self, **kwargs: Any) -> LLMReply:
        self.checkouts.append(self._engine.sync_engine.pool.checkedout())
        return await super().create_message(**kwargs)


@pytest.fixture
def db_url(tmp_path: object) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/conn.db"  # type: ignore[operator]


async def test_no_connection_is_held_across_llm_calls(db_url: str) -> None:
    db = Database(db_url)
    await db.create_all()
    settings = Settings()
    probe = _PoolProbeLLM(db.engine)
    service = ChatService(
        uow=SqlUnitOfWork(db.sessionmaker),
        catalog=KeywordCatalogSearch.from_file(CATALOG),
        llm=probe,
        evaluator=LLMEvaluator(
            probe,
            model=settings.eval_model,
            max_tokens=settings.eval_max_tokens,
            flag_threshold=settings.flag_confidence_threshold,
        ),
        notifier=NullNotifier(),
        settings=settings,
    )

    await service.handle(user_id="u", message="enterprise pricing?", session_id=None)
    await db.dispose()

    # The model was actually called (agent loop + evaluator)...
    assert len(probe.checkouts) >= 2
    # ...and not once was a DB connection held while it ran.
    assert all(c == 0 for c in probe.checkouts), probe.checkouts
