"""The native tool-use loop.

Provider-neutral: it speaks only the domain's ConvMessage/part types and the LLMPort.
It runs the model, dispatches any tool_use blocks through the registry, feeds the
tool_result blocks back, and repeats until the model stops calling tools (or a hard
iteration cap trips). It collects the tools actually invoked and the tool outputs (which
become the grounding context handed to the evaluator).
"""

from dataclasses import dataclass

from app.agents.tool_registry import ToolRegistry
from app.domain.ports import LLMPort
from app.domain.types import ConvMessage, Part, TextPart, ToolResultPart, ToolUsePart


@dataclass(frozen=True)
class AgentOutcome:
    answer: str
    tools_called: list[str]
    context: str  # concatenated tool outputs — the grounding the evaluator scores against


def _dedupe(names: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


class AgentLoop:
    def __init__(
        self,
        llm: LLMPort,
        registry: ToolRegistry,
        *,
        model: str,
        max_tokens: int,
        max_iterations: int,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._model = model
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations

    @staticmethod
    def _text_of(message: ConvMessage) -> str:
        return "\n".join(p.text for p in message.parts if isinstance(p, TextPart))

    async def run(self, *, system: str, user_message: str) -> AgentOutcome:
        messages: list[ConvMessage] = [ConvMessage("user", [TextPart(user_message)])]
        specs = self._registry.specs()
        tools_called: list[str] = []
        tool_outputs: list[str] = []
        answer = ""

        for _ in range(self._max_iterations):
            reply = await self._llm.create_message(
                model=self._model,
                system=system,
                messages=messages,
                tools=specs,
                max_tokens=self._max_tokens,
            )
            messages.append(reply.message)
            tool_uses = [p for p in reply.message.parts if isinstance(p, ToolUsePart)]

            if reply.stop_reason != "tool_use" or not tool_uses:
                answer = self._text_of(reply.message)
                break

            result_parts: list[Part] = []
            for call in tool_uses:
                tools_called.append(call.name)
                output = await self._registry.dispatch(call.name, call.arguments)
                tool_outputs.append(output)
                result_parts.append(ToolResultPart(tool_use_id=call.id, content=output))
            messages.append(ConvMessage("user", result_parts))
        else:
            # Iteration cap hit without a natural stop: salvage the latest assistant text.
            answer = next(
                (
                    self._text_of(m)
                    for m in reversed(messages)
                    if m.role == "assistant" and self._text_of(m)
                ),
                "",
            )

        if not answer.strip():
            answer = "I'm sorry — I couldn't find enough grounded information to answer that."

        return AgentOutcome(
            answer=answer.strip(),
            tools_called=_dedupe(tools_called),
            context="\n".join(tool_outputs),
        )
