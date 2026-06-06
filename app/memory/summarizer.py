"""Rolling memory summarization (bonus).

Instead of replaying every turn forever, once a user's history grows past a threshold we
fold the older turns (everything except the most recent window) into a compact rolling
summary, advancing `up_to_seq`. get_user_memory then serves summary + recent turns, keeping
context bounded while preserving continuity.
"""

from app.agents.prompts import SUMMARIZER_SYSTEM
from app.domain.ports import LLMPort, MemoryPort
from app.domain.types import ConvMessage, TextPart


class Summarizer:
    def __init__(
        self,
        llm: LLMPort,
        *,
        model: str,
        max_tokens: int,
        recent_window: int,
        summarize_after: int,
    ) -> None:
        self._llm = llm
        self._model = model
        self._max_tokens = max_tokens
        self._recent_window = recent_window
        self._summarize_after = summarize_after

    async def run(self, memory: MemoryPort, user_id: str) -> bool:
        """Fold old turns into the rolling summary. Returns True if it updated anything."""
        total = await memory.count_turns(user_id)
        if total <= self._summarize_after:
            return False

        history = await memory.get_history(user_id)
        state = await memory.get_summary_state(user_id)
        up_to = state.up_to_seq if state else 0

        unfolded = [t for t in history if (t.seq or 0) > up_to]
        # Keep the most recent window verbatim; only fold what is older than it.
        if len(unfolded) <= self._recent_window:
            return False
        to_fold = unfolded[: len(unfolded) - self._recent_window]
        if not to_fold:
            return False

        new_up_to = max((t.seq or 0) for t in to_fold)
        transcript = "\n".join(f"{t.role}: {t.content}" for t in to_fold)
        prompt = (
            f"Existing summary:\n{(state.summary if state else '') or '(none yet)'}\n\n"
            f"New turns to fold in:\n{transcript}\n\n"
            "Produce an updated, concise summary (under ~150 words)."
        )
        reply = await self._llm.create_message(
            model=self._model,
            system=SUMMARIZER_SYSTEM,
            messages=[ConvMessage("user", [TextPart(prompt)])],
            tools=[],
            max_tokens=self._max_tokens,
        )
        summary = "\n".join(
            p.text for p in reply.message.parts if isinstance(p, TextPart)
        ).strip()
        if not summary:
            return False

        await memory.upsert_summary(user_id=user_id, summary=summary, up_to_seq=new_up_to)
        return True
