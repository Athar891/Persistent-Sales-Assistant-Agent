"""The composition root.

This is the *only* place concrete adapters are constructed and handed to services as
ports. Singletons (DB, catalog, LLM, notifier) live on app.state, set at startup; the
request-scoped DB session and the per-request services are assembled here via Depends.
"""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.db.unit_of_work import SqlUnitOfWork
from app.domain.ports import CatalogPort, LLMPort, NotifierPort, ReviewLogPort, UnitOfWork
from app.reviews.sql_review_log import SqlReviewLog
from app.services.chat_service import ChatService
from app.services.eval_service import LLMEvaluator
from app.settings import Settings, get_settings


def get_settings_dep() -> Settings:
    return get_settings()


def get_db(request: Request) -> Database:
    return cast(Database, request.app.state.db)


def get_catalog(request: Request) -> CatalogPort:
    return cast(CatalogPort, request.app.state.catalog)


def get_llm(request: Request) -> LLMPort:
    return cast(LLMPort, request.app.state.llm)


def get_notifier(request: Request) -> NotifierPort:
    return cast(NotifierPort, request.app.state.notifier)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session/transaction per request: commit on success, roll back on error."""
    db = cast(Database, request.app.state.db)
    async with db.sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbDep = Annotated[Database, Depends(get_db)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CatalogDep = Annotated[CatalogPort, Depends(get_catalog)]
LLMDep = Annotated[LLMPort, Depends(get_llm)]
NotifierDep = Annotated[NotifierPort, Depends(get_notifier)]


def get_uow(db: DbDep) -> UnitOfWork:
    """A factory of short-lived transactions. /chat opens several, never one long one."""
    return SqlUnitOfWork(db.sessionmaker)


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


def get_review_log(session: SessionDep) -> ReviewLogPort:
    return SqlReviewLog(session)


ReviewLogDep = Annotated[ReviewLogPort, Depends(get_review_log)]


def get_chat_service(
    uow: UowDep,
    catalog: CatalogDep,
    llm: LLMDep,
    notifier: NotifierDep,
    settings: SettingsDep,
) -> ChatService:
    evaluator = LLMEvaluator(
        llm,
        model=settings.eval_model,
        max_tokens=settings.eval_max_tokens,
        flag_threshold=settings.flag_confidence_threshold,
    )
    return ChatService(
        uow=uow,
        catalog=catalog,
        llm=llm,
        evaluator=evaluator,
        notifier=notifier,
        settings=settings,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
