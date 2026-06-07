"""Ports — the abstract boundaries of the hexagon.

Every port is a ``typing.Protocol``. Concrete adapters implement them structurally
(no inheritance needed) and are wired exactly once via FastAPI dependency injection.
Nothing in services/ or agents/ may import a concrete adapter; they depend only on
these protocols. That single rule is what makes the storage and LLM backends
swappable in one file.
"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from app.domain.types import (
    ConvMessage,
    EvalAggregate,
    LLMReply,
    ReviewEntry,
    SummaryState,
    ToolSpec,
    Turn,
)
from app.models.catalog import Plan
from app.models.eval import EvalBlock, EvalResult


class MemoryPort(Protocol):
    """Persistent, cross-session memory. The one seam swapping SQLite↔Postgres↔Mem0."""

    async def append_message(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        tools_called: list[str] | None = None,
    ) -> Turn: ...

    async def get_history(self, user_id: str) -> list[Turn]:
        """All turns across all sessions, oldest first."""
        ...

    async def get_recent_turns(self, user_id: str, limit: int) -> list[Turn]:
        """The most recent ``limit`` turns, oldest first."""
        ...

    async def count_turns(self, user_id: str) -> int: ...

    async def get_summary_state(self, user_id: str) -> SummaryState | None: ...

    async def upsert_summary(self, *, user_id: str, summary: str, up_to_seq: int) -> None: ...

    async def wipe_user(self, user_id: str) -> int:
        """GDPR reset: delete all stored data for a user. Returns rows removed."""
        ...


class CatalogPort(Protocol):
    """Read-only product catalog access. In-memory, so methods are synchronous."""

    def get_all(self) -> list[Plan]: ...

    def search(self, query: str) -> list[Plan]: ...


class LLMPort(Protocol):
    """A provider-neutral single model call. The agent loop owns iteration."""

    async def create_message(
        self,
        *,
        model: str,
        system: str,
        messages: list[ConvMessage],
        tools: list[ToolSpec],
        max_tokens: int,
        force_tool: str | None = None,
    ) -> LLMReply: ...


class EvaluatorPort(Protocol):
    """Produces a structured self-evaluation for a draft answer."""

    async def evaluate(
        self, *, user_message: str, context: str, draft_answer: str
    ) -> EvalResult: ...


class ReviewLogPort(Protocol):
    """Persistent log of responses escalated for human review."""

    async def record(
        self,
        *,
        user_id: str,
        session_id: str,
        reason: str,
        evaluation: EvalBlock | None = None,
        message_id: int | None = None,
    ) -> None: ...

    async def list_entries(
        self, *, user_id: str | None = None, only_unresolved: bool = False, limit: int = 100
    ) -> list[ReviewEntry]: ...


class EvalStorePort(Protocol):
    """Persists every self-evaluation and answers the aggregation query."""

    async def record(
        self, *, message_id: int, user_id: str, session_id: str, evaluation: EvalBlock
    ) -> None: ...

    async def aggregate(self, user_id: str, *, high_confidence_threshold: float) -> EvalAggregate:
        ...


class NotifierPort(Protocol):
    """Escalation sink for flagged responses (logging now; pager/Slack at scale)."""

    async def notify(
        self, *, user_id: str, session_id: str, reason: str, evaluation: EvalBlock | None = None
    ) -> None: ...


@dataclass(frozen=True)
class Repositories:
    """The SQL-backed ports bound to one short-lived transaction (see ``UnitOfWork``)."""

    memory: MemoryPort
    evals: EvalStorePort
    reviews: ReviewLogPort


class UnitOfWork(Protocol):
    """Opens a short transaction that exposes the repositories.

    Each ``begin()`` block is one commit/rollback scope, and it releases its pooled DB
    connection the moment the block exits — so no connection is held while the agent or
    evaluator awaits the LLM. A /chat turn is a *sequence* of these short transactions,
    never one long transaction spanning every model round-trip.
    """

    def begin(self) -> AbstractAsyncContextManager[Repositories]: ...
