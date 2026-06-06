"""Async engine + session factory, keyed off ``DATABASE_URL``.

The whole point of the memory abstraction is that this is the *only* place the
storage engine is chosen. Swapping SQLite for Postgres is a URL change, not a
code change — ``normalize_database_url`` makes both speak async SQLAlchemy.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base

# Query params that libpq/psycopg accept but asyncpg rejects outright.
_ASYNC_INCOMPATIBLE_PARAMS = {"sslmode", "channel_binding"}


def normalize_database_url(url: str) -> str:
    """Coerce any Postgres URL to the asyncpg driver and drop asyncpg-hostile params.

    Railway and Heroku hand out ``postgres://`` / ``postgresql://`` (sometimes with
    ``?sslmode=require``); async SQLAlchemy needs ``postgresql+asyncpg://`` and asyncpg
    does not understand libpq-style ``sslmode``. SQLite URLs pass through untouched.
    """
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    parts = urlsplit(url)
    if parts.query:
        kept = [(k, v) for k, v in parse_qsl(parts.query) if k not in _ASYNC_INCOMPATIBLE_PARAMS]
        url = urlunsplit(parts._replace(query=urlencode(kept)))
    return url


class Database:
    """Owns the async engine and session factory for the app's lifetime."""

    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(normalize_database_url(url), future=True)
        self.sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    async def create_all(self) -> None:
        """Create tables from metadata. Used by tests/local dev; prod uses Alembic."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def ping(self) -> bool:
        """Real connectivity check for /health."""
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def dispose(self) -> None:
        await self.engine.dispose()
