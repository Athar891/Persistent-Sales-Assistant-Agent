"""Self-evaluation schema — present on every /chat response and persisted."""

from dataclasses import dataclass

from pydantic import BaseModel, Field


class EvalBlock(BaseModel):
    """Structured self-score. Validated, never free-text-parsed."""

    groundedness: float = Field(ge=0.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    flagged: bool
    reasoning: str


@dataclass(frozen=True)
class EvalResult:
    """An evaluation plus whether it was a genuine structured measurement.

    A degraded result — the evaluator returned no structured score — is surfaced for human
    review but not persisted, so its placeholder zeros never drag down the /evals averages.
    """

    block: EvalBlock
    evaluated: bool


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
