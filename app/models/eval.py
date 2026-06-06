"""Self-evaluation schema — present on every /chat response and persisted."""

from pydantic import BaseModel, Field


class EvalBlock(BaseModel):
    """Structured self-score. Validated, never free-text-parsed."""

    groundedness: float = Field(ge=0.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    flagged: bool
    reasoning: str
