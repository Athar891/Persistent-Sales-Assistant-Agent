"""The contract every agent tool implements.

A tool advertises a `spec` (name + description + JSON input schema) to the model and
exposes an async `run` that executes it and returns a plain-text result destined for
a tool_result block. Tools depend on ports, never on concrete adapters.
"""

from typing import Any, Protocol

from app.domain.types import ToolSpec


class Tool(Protocol):
    @property
    def spec(self) -> ToolSpec: ...

    async def run(self, arguments: dict[str, Any]) -> str: ...
