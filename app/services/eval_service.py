"""LLMEvaluator — the default EvaluatorPort.

Earns the eval block rather than faking it: a second (cheap) Claude call scores the draft
answer against the grounding context, returned through a *forced* `submit_evaluation` tool
so the output is structured and Pydantic-validated — never free-text parsed. The flag
threshold is authoritative: the server sets `flagged`, not the model.
"""

from typing import Any

from app.agents.prompts import EVAL_SYSTEM
from app.domain.ports import LLMPort
from app.domain.types import ConvMessage, TextPart, ToolSpec, ToolUsePart
from app.models.eval import EvalBlock, EvalResult

_EVAL_TOOL = ToolSpec(
    name="submit_evaluation",
    description="Submit the structured self-evaluation of the draft answer.",
    input_schema={
        "type": "object",
        "properties": {
            "groundedness": {
                "type": "number",
                "description": "0-1: how fully the answer is supported by the provided context.",
            },
            "relevance": {
                "type": "number",
                "description": "0-1: how well the answer addresses the user's question.",
            },
            "confidence": {
                "type": "number",
                "description": "0-1: overall confidence the answer is correct and safe to send.",
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences explaining the scores.",
            },
        },
        "required": ["groundedness", "relevance", "confidence", "reasoning"],
    },
)


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


class LLMEvaluator:
    def __init__(self, llm: LLMPort, *, model: str, max_tokens: int, flag_threshold: float) -> None:
        self._llm = llm
        self._model = model
        self._max_tokens = max_tokens
        self._flag_threshold = flag_threshold

    async def evaluate(self, *, user_message: str, context: str, draft_answer: str) -> EvalResult:
        prompt = (
            "Evaluate the assistant's draft answer.\n\n"
            f"User question:\n{user_message}\n\n"
            "Retrieved context the answer should rely on (catalog + remembered history):\n"
            f"{context or '(no tools were called)'}\n\n"
            f"Draft answer:\n{draft_answer}\n\n"
            "Call submit_evaluation with calibrated scores in [0,1]. Be strict: if the answer "
            "asserts facts not present in the context, lower groundedness and confidence."
        )
        reply = await self._llm.create_message(
            model=self._model,
            system=EVAL_SYSTEM,
            messages=[ConvMessage("user", [TextPart(prompt)])],
            tools=[_EVAL_TOOL],
            max_tokens=self._max_tokens,
            force_tool=_EVAL_TOOL.name,
        )
        args = self._extract(reply.message.parts)
        if args is None:
            # No structured output — fail safe by flagging, but mark it un-evaluated so the
            # placeholder zeros are kept out of the persisted /evals aggregates.
            degraded = EvalBlock(
                groundedness=0.0,
                relevance=0.0,
                confidence=0.0,
                flagged=True,
                reasoning="Evaluator did not return a structured score; flagged for review.",
            )
            return EvalResult(block=degraded, evaluated=False)

        confidence = _clamp(args.get("confidence"))
        # Authoritative: the threshold decides flagging, regardless of what the model says.
        block = EvalBlock(
            groundedness=_clamp(args.get("groundedness")),
            relevance=_clamp(args.get("relevance")),
            confidence=confidence,
            flagged=confidence < self._flag_threshold,
            reasoning=str(args.get("reasoning") or "No reasoning returned."),
        )
        return EvalResult(block=block, evaluated=True)

    @staticmethod
    def _extract(parts: list[Any]) -> dict[str, Any] | None:
        for part in parts:
            if isinstance(part, ToolUsePart) and part.name == _EVAL_TOOL.name:
                return part.arguments
        return None
