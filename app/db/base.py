"""SQLAlchemy declarative base shared by all ORM models."""

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Timezone-aware UTC now. Used as the column default for all timestamps."""
    return datetime.now(UTC)
