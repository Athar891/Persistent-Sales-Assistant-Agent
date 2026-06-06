"""Self-evaluation schema — present on every /chat response and persisted."""

from pydantic import BaseModel, Field


class EvalBlock(BaseModel):
    """Structured self-score. Validated, never free-text-parsed."""

    groundedness: float = Field(ge=0.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    flagged: bool
    reasoning: str


class EvalSummary(BaseModel):
    """Aggregated eval stats for one user (GET /chat/{user_id}/evals)."""

    user_id: str
    total_responses: int
    high_confidence: int
    high_confidence_pct: float
    flagged: int
    avg_groundedness: float
    avg_relevance: float
    avg_confidence: float
