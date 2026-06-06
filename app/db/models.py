"""ORM tables.

Design notes:
- Integer autoincrement PKs give a stable, gap-tolerant ordering key (``id``) that
  works identically on SQLite and Postgres — cleaner than ordering by timestamp,
  which can tie. ``up_to_seq`` on summaries points at the highest message id folded in.
- ``session_id`` is a UUID string minted per conversation; ``user_id`` is a free-form
  client identifier (no pre-registration), so it is a plain indexed string, not a FK.
- Types are deliberately portable (String/Text/Float/Boolean/JSON, TZ-aware DateTime)
  so the same models run on SQLite locally and Postgres in production unchanged.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class Message(Base):
    """One conversational turn (user or assistant). Source of truth for history."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    # Tools the agent invoked to produce an assistant turn; null for user turns.
    tools_called: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_messages_user_id_id", "user_id", "id"),)


class Eval(Base):
    """Self-evaluation attached to exactly one assistant message."""

    __tablename__ = "evals"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    session_id: Mapped[str] = mapped_column(String(36))
    groundedness: Mapped[float] = mapped_column(Float)
    relevance: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    reasoning: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemorySummary(Base):
    """Rolling, compressed summary of a user's older turns (one row per user)."""

    __tablename__ = "memory_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    summary: Mapped[str] = mapped_column(Text)
    up_to_seq: Mapped[int] = mapped_column(default=0)  # highest message.id folded in
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class HumanReviewLog(Base):
    """Escalation row written when a response is flagged for human review."""

    __tablename__ = "human_review_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    session_id: Mapped[str] = mapped_column(String(36))
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), default=None
    )
    reason: Mapped[str] = mapped_column(Text)
    groundedness: Mapped[float] = mapped_column(Float)
    relevance: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
