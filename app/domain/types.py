"""Framework-free domain types.

These are the vocabulary the core (services, agents, ports) speaks. They carry no
SQLAlchemy or HTTP concerns and — crucially — no Anthropic SDK types, so the LLM
adapter can be swapped without touching the agent loop. Pydantic *schemas* that
cross the API boundary live in app/models; these dataclasses stay internal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Turn:
    """A persisted conversational turn, as the memory layer hands it back."""

    role: str  # "user" | "assistant"
    content: str
    session_id: str | None = None
    tools_called: list[str] | None = None
    created_at: datetime | None = None
    seq: int | None = None  # the message id — a stable, monotonic ordering key


@dataclass(frozen=True)
class SummaryState:
    """A user's rolling summary plus the highest turn id it already folds in."""

    summary: str
    up_to_seq: int


@dataclass(frozen=True)
class EvalAggregate:
    """Aggregated eval stats for a user (powers GET /chat/{user_id}/evals)."""

    total: int
    flagged: int
    high_confidence: int
    high_confidence_pct: float
    avg_groundedness: float
    avg_relevance: float
    avg_confidence: float


@dataclass(frozen=True)
class ReviewEntry:
    """A human-review-log row, as the review store hands it back."""

    id: int
    user_id: str
    session_id: str
    message_id: int | None
    reason: str
    groundedness: float | None
    relevance: float | None
    confidence: float | None
    resolved: bool
    created_at: datetime


# --- LLM conversation primitives (provider-neutral) ---------------------------
# The agent loop manipulates these; the LLM adapter translates them to/from the
# concrete provider's wire format (Anthropic tool_use / tool_result blocks).


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ToolUsePart:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResultPart:
    tool_use_id: str
    content: str


Part = TextPart | ToolUsePart | ToolResultPart


@dataclass(frozen=True)
class ConvMessage:
    role: str  # "user" | "assistant"
    parts: list[Part]


@dataclass(frozen=True)
class LLMReply:
    message: ConvMessage  # the assistant turn (text and/or tool_use parts)
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens" | ...


@dataclass(frozen=True)
class ToolSpec:
    """A tool advertised to the model: name, description, JSON input schema."""

    name: str
    description: str
    input_schema: dict[str, Any]
