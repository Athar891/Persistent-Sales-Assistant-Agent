"""Shared test doubles. A scripted LLMPort lets tests drive the agent/eval loops
deterministically and offline — no Anthropic key, no cost, no flakiness.
"""

from typing import Any

from app.domain.types import ConvMessage, LLMReply, TextPart, ToolSpec, ToolUsePart


class ScriptedLLM:
    """Returns queued replies in order; records every call for assertions."""

    def __init__(self, replies: list[LLMReply] | None = None) -> None:
        self._replies = list(replies or [])
        self.calls: list[dict[str, Any]] = []

    async def create_message(
        self,
        *,
        model: str,
        system: str,
        messages: list[ConvMessage],
        tools: list[ToolSpec],
        max_tokens: int,
        force_tool: str | None = None,
    ) -> LLMReply:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": list(messages),
                "tools": tools,
                "force_tool": force_tool,
            }
        )
        if self._replies:
            return self._replies.pop(0)
        return LLMReply(ConvMessage("assistant", [TextPart("")]), "end_turn")


def tool_use(tool_id: str, name: str, arguments: dict[str, Any]) -> LLMReply:
    return LLMReply(ConvMessage("assistant", [ToolUsePart(tool_id, name, arguments)]), "tool_use")


def final_text(text: str) -> LLMReply:
    return LLMReply(ConvMessage("assistant", [TextPart(text)]), "end_turn")
