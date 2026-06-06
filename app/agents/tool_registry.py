"""Maps tool names to tool instances and dispatches calls from the agent loop."""

from typing import Any

from app.domain.types import ToolSpec
from app.tools.base import Tool


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools: dict[str, Tool] = {t.spec.name: t for t in tools}

    def specs(self) -> list[ToolSpec]:
        """The tool specs advertised to the model (stable order = cache-friendly)."""
        return [t.spec for t in self._tools.values()]

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'."
        try:
            return await tool.run(arguments)
        except Exception as exc:
            # return it as an (error) tool_result so the model can recover or apologise.
            return f"Error running {name}: {exc}"
