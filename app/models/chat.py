"""Request/response schemas for the chat endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.eval import EvalBlock


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    # Optional: supply to continue a session. Omitted → the server mints a new one.
    # Cross-session memory always keys on the path's user_id, never on session_id.
    session_id: str | None = None


class ChatData(BaseModel):
    """The brief's mandated /chat payload, verbatim (lives inside the envelope's data)."""

    response: str
    eval: EvalBlock
    tools_called: list[str]
    session_id: str


class HistoryTurn(BaseModel):
    seq: int
    session_id: str
    role: str
    content: str
    tools_called: list[str] | None = None
    created_at: datetime


class ChatHistory(BaseModel):
    user_id: str
    count: int
    turns: list[HistoryTurn]


class MemoryWipeResult(BaseModel):
    user_id: str
    deleted_rows: int
