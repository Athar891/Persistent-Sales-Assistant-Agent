"""Schemas for the human-review-log query endpoint (bonus)."""

from datetime import datetime

from pydantic import BaseModel


class ReviewLogEntry(BaseModel):
    id: int
    user_id: str
    session_id: str
    message_id: int | None = None
    reason: str
    groundedness: float | None = None
    relevance: float | None = None
    confidence: float | None = None
    resolved: bool
    created_at: datetime


class ReviewLog(BaseModel):
    count: int
    entries: list[ReviewLogEntry]
