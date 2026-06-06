"""Shared test doubles. A scripted LLMPort lets tests drive the agent/eval loops
deterministically and offline — no Anthropic key, no cost, no flakiness.
"""

from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient

from app.db.session import Database
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


class StubLLM:
    """A behavioral fake for full-stack tests.

    Drives a realistic agent loop (get_user_memory → search_catalog → answer) by inspecting
    which tools have been requested so far, and returns a structured score when the evaluator
    forces submit_evaluation. `confidence` is tunable so a test can force a flag.
    """

    def __init__(
        self,
        *,
        confidence: float = 0.9,
        answer: str = "Our Enterprise plan is $499/mo and includes SSO and audit logs.",
    ) -> None:
        self.confidence = confidence
        self.answer = answer
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
        self.calls.append({"system": system, "messages": list(messages), "force_tool": force_tool})

        if force_tool == "submit_evaluation":
            return LLMReply(
                ConvMessage(
                    "assistant",
                    [
                        ToolUsePart(
                            "ev",
                            "submit_evaluation",
                            {
                                "groundedness": 0.9,
                                "relevance": 0.9,
                                "confidence": self.confidence,
                                "reasoning": "Grounded in catalog and remembered context.",
                            },
                        )
                    ],
                ),
                "tool_use",
            )

        requested = {p.name for m in messages for p in m.parts if isinstance(p, ToolUsePart)}
        if "get_user_memory" not in requested:
            return tool_use("m1", "get_user_memory", {})
        if "search_catalog" not in requested:
            return tool_use("c1", "search_catalog", {"query": "enterprise sso pricing"})
        return final_text(self.answer)


@dataclass
class Harness:
    """Bundle returned by the `harness` fixture: an HTTP client plus the stubbed LLM and DB."""

    client: AsyncClient
    llm: StubLLM
    db: Database

