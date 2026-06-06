"""get_user_memory — a real callable tool that injects this user's past context.

The user_id is bound server-side (from the request path), not chosen by the model — the
model never gets to ask for another user's memory. The tool surfaces the rolling summary
plus the most recent verbatim turns, which is what "relevant past facts" means here.
"""

from typing import Any

from app.domain.ports import MemoryPort
from app.domain.types import ToolSpec

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Optional topic to focus the recall on; omit to get general context.",
        }
    },
    "required": [],
}


class GetUserMemoryTool:
    name = "get_user_memory"

    def __init__(self, memory: MemoryPort, user_id: str, *, recent_window: int) -> None:
        self._memory = memory
        self._user_id = user_id
        self._recent_window = recent_window

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=(
                "Retrieve relevant past facts about the current user — a summary of earlier "
                "sessions plus their most recent turns. Call this at the start of a turn to "
                "recall what they have already discussed."
            ),
            input_schema=_INPUT_SCHEMA,
        )

    async def run(self, arguments: dict[str, Any]) -> str:
        state = await self._memory.get_summary_state(self._user_id)
        recent = await self._memory.get_recent_turns(self._user_id, self._recent_window)

        if state is None and not recent:
            return "No prior conversation found for this user."

        lines: list[str] = []
        if state is not None and state.summary:
            lines.append(f"Summary of earlier conversation: {state.summary}")
        if recent:
            lines.append("Recent turns (oldest first):")
            lines.extend(f"- {turn.role}: {turn.content}" for turn in recent)
        return "\n".join(lines)
