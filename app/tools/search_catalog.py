"""search_catalog — a real callable tool over the product catalog.

This is how the agent answers pricing/feature questions: it calls this function and
grounds its reply in the returned rows, rather than reciting plans from model memory.
"""

from typing import Any

from app.domain.ports import CatalogPort
from app.domain.types import ToolSpec
from app.models.catalog import Plan

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Keywords describing what the user wants, e.g. "
                "'enterprise sso pricing' or 'plan with webhooks'."
            ),
        }
    },
    "required": ["query"],
}


def _format(plans: list[Plan]) -> str:
    if not plans:
        return "No matching plans found in the catalog."
    return "\n".join(f"{p.name} — {p.price}: {', '.join(p.features)}" for p in plans)


class SearchCatalogTool:
    name = "search_catalog"

    def __init__(self, catalog: CatalogPort) -> None:
        self._catalog = catalog

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=(
                "Search the product/pricing catalog by keyword. Use this for ANY question "
                "about plans, prices, features, limits, or what a tier includes — never "
                "answer pricing or feature questions from your own memory."
            ),
            input_schema=_INPUT_SCHEMA,
        )

    async def run(self, arguments: dict[str, Any]) -> str:
        query = str(arguments.get("query", "")).strip()
        results = self._catalog.search(query) if query else self._catalog.get_all()
        return _format(results)
