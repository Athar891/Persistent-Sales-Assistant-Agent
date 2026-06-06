"""flag_for_human — escalate a conversation to a human reviewer.

A single real callable with two invocation paths:
- the agent may call it as a tool to self-escalate (`run`); and
- the chat service calls `escalate` deterministically after evaluation whenever
  confidence falls below the threshold (the authoritative trigger).

Both paths write a human_review_log row via the ReviewLogPort and notify via the
NotifierPort. user_id/session_id are bound server-side, never chosen by the model.
"""

from typing import Any

from app.domain.ports import NotifierPort, ReviewLogPort
from app.domain.types import ToolSpec
from app.models.eval import EvalBlock


class FlagForHumanTool:
    name = "flag_for_human"

    def __init__(
        self,
        reviews: ReviewLogPort,
        notifier: NotifierPort,
        *,
        user_id: str,
        session_id: str,
    ) -> None:
        self._reviews = reviews
        self._notifier = notifier
        self._user_id = user_id
        self._session_id = session_id

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=(
                "Escalate this conversation to a human reviewer when you cannot answer "
                "confidently or safely. Provide a short reason."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why this needs a human."}
                },
                "required": ["reason"],
            },
        )

    async def run(self, arguments: dict[str, Any]) -> str:
        reason = str(arguments.get("reason") or "(no reason given)")
        await self.escalate(reason=f"Model-initiated: {reason}")
        return "Escalated to a human reviewer."

    async def escalate(
        self, *, reason: str, evaluation: EvalBlock | None = None, message_id: int | None = None
    ) -> None:
        await self._reviews.record(
            user_id=self._user_id,
            session_id=self._session_id,
            reason=reason,
            evaluation=evaluation,
            message_id=message_id,
        )
        await self._notifier.notify(
            user_id=self._user_id,
            session_id=self._session_id,
            reason=reason,
            evaluation=evaluation,
        )
