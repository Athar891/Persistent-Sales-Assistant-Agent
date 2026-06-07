"""The eval block must be earned and structured (rubric: structured? always present?
not a random number?). The threshold — not the model — decides `flagged`.
"""

from typing import Any

from app.domain.types import ConvMessage, LLMReply, ToolUsePart
from app.services.eval_service import LLMEvaluator
from tests.support import ScriptedLLM, final_text


def _eval_reply(**scores: Any) -> LLMReply:
    return LLMReply(
        ConvMessage("assistant", [ToolUsePart("e1", "submit_evaluation", scores)]), "tool_use"
    )


async def test_high_confidence_is_not_flagged_and_forces_the_eval_tool() -> None:
    llm = ScriptedLLM(
        [_eval_reply(groundedness=0.95, relevance=0.9, confidence=0.85, reasoning="grounded")]
    )
    evaluator = LLMEvaluator(llm, model="m", max_tokens=256, flag_threshold=0.7)
    result = await evaluator.evaluate(user_message="q", context="ctx", draft_answer="a")
    block = result.block

    assert result.evaluated is True
    assert block.flagged is False
    assert block.confidence == 0.85
    assert block.reasoning == "grounded"
    assert llm.calls[0]["force_tool"] == "submit_evaluation"  # structured output, not free text


async def test_low_confidence_is_flagged() -> None:
    llm = ScriptedLLM(
        [_eval_reply(groundedness=0.4, relevance=0.5, confidence=0.5, reasoning="weak")]
    )
    evaluator = LLMEvaluator(llm, model="m", max_tokens=256, flag_threshold=0.7)
    block = (await evaluator.evaluate(user_message="q", context="", draft_answer="a")).block
    assert block.flagged is True


async def test_threshold_boundary_is_not_flagged() -> None:
    llm = ScriptedLLM(
        [_eval_reply(groundedness=0.7, relevance=0.7, confidence=0.7, reasoning="ok")]
    )
    evaluator = LLMEvaluator(llm, model="m", max_tokens=256, flag_threshold=0.7)
    block = (await evaluator.evaluate(user_message="q", context="c", draft_answer="a")).block
    assert block.flagged is False  # confidence < threshold is strict; 0.7 < 0.7 is False


async def test_out_of_range_scores_are_clamped() -> None:
    llm = ScriptedLLM([_eval_reply(groundedness=1.5, relevance=-0.2, confidence=2, reasoning="x")])
    evaluator = LLMEvaluator(llm, model="m", max_tokens=256, flag_threshold=0.7)
    block = (await evaluator.evaluate(user_message="q", context="c", draft_answer="a")).block
    assert (block.groundedness, block.relevance, block.confidence) == (1.0, 0.0, 1.0)


async def test_missing_structured_output_fails_safe_to_flagged() -> None:
    llm = ScriptedLLM([final_text("looks fine to me")])  # model didn't call the tool
    evaluator = LLMEvaluator(llm, model="m", max_tokens=256, flag_threshold=0.7)
    result = await evaluator.evaluate(user_message="q", context="c", draft_answer="a")
    assert result.evaluated is False
    assert result.block.flagged is True
    assert result.block.confidence == 0.0
