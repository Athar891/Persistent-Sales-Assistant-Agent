"""AnthropicClient — the default LLMPort adapter (async Anthropic SDK, native tool use).

This is the only module in the app that imports the Anthropic SDK. It translates the
domain's provider-neutral conversation primitives to/from Anthropic content blocks, so
swapping providers means rewriting this one file — the agent loop never changes.
"""

from typing import Any, cast

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import Message, TextBlock, ToolUseBlock

from app.domain.errors import ConfigurationError, UpstreamLLMError
from app.domain.types import (
    ConvMessage,
    LLMReply,
    Part,
    TextPart,
    ToolResultPart,
    ToolSpec,
    ToolUsePart,
)


def _content_blocks(message: ConvMessage) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for part in message.parts:
        if isinstance(part, TextPart):
            blocks.append({"type": "text", "text": part.text})
        elif isinstance(part, ToolUsePart):
            blocks.append(
                {"type": "tool_use", "id": part.id, "name": part.name, "input": part.arguments}
            )
        elif isinstance(part, ToolResultPart):
            blocks.append(
                {"type": "tool_result", "tool_use_id": part.tool_use_id, "content": part.content}
            )
    return blocks


def _parse_reply(message: Message) -> LLMReply:
    parts: list[Part] = []
    for block in message.content:
        if isinstance(block, TextBlock):
            parts.append(TextPart(text=block.text))
        elif isinstance(block, ToolUseBlock):
            parts.append(
                ToolUsePart(
                    id=block.id,
                    name=block.name,
                    arguments=cast("dict[str, Any]", block.input),
                )
            )
    return LLMReply(
        message=ConvMessage(role="assistant", parts=parts),
        stop_reason=message.stop_reason or "end_turn",
    )


class AnthropicClient:
    def __init__(self, api_key: str | None) -> None:
        # Built only when a key is present so the app still boots (health, catalog)
        # without one; LLM-backed calls then fail fast with a 503 Problem Details.
        self._client = AsyncAnthropic(api_key=api_key) if api_key else None

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
        if self._client is None:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY is not set; the agent cannot reach Claude."
            )

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": _content_blocks(m)} for m in messages],
        }
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ]
            kwargs["tool_choice"] = (
                {"type": "tool", "name": force_tool} if force_tool else {"type": "auto"}
            )

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:  # SDK base error (network, 4xx, 5xx)
            raise UpstreamLLMError(f"Anthropic request failed: {exc}") from exc

        return _parse_reply(response)
