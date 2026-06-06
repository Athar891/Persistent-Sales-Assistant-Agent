"""KeywordCatalogSearch — the default CatalogPort adapter.

Deliberately *not* a vector store. The catalog is three plans; token-overlap scoring
with a small partial-match bonus is correct, debuggable, and dependency-free. The
README is honest about this, and the CatalogPort boundary means a semantic adapter
could replace it without touching a single caller.
"""

import json
import re
from pathlib import Path

from app.models.catalog import Catalog, Plan

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def load_catalog(path: str) -> Catalog:
    """Load and validate catalog.json against the Pydantic schema."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Catalog.model_validate(data)


class KeywordCatalogSearch:
    def __init__(self, plans: list[Plan]) -> None:
        self._plans = list(plans)
        self._index: list[tuple[Plan, set[str]]] = [
            (p, _tokenize(f"{p.name} {p.price} {' '.join(p.features)}")) for p in self._plans
        ]

    @classmethod
    def from_file(cls, path: str) -> "KeywordCatalogSearch":
        return cls(load_catalog(path).plans)

    def get_all(self) -> list[Plan]:
        return list(self._plans)

    def search(self, query: str) -> list[Plan]:
        q = _tokenize(query)
        if not q:
            return list(self._plans)

        scored: list[tuple[int, int, Plan]] = []
        for idx, (plan, tokens) in enumerate(self._index):
            score = self._score(q, tokens)
            if score > 0:
                # -idx as secondary key preserves catalog order on score ties.
                scored.append((score, -idx, plan))

        if not scored:
            # No overlap at all — return the whole catalog so the agent still has context.
            return list(self._plans)

        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return [plan for _, _, plan in scored]

    @staticmethod
    def _score(query_tokens: set[str], plan_tokens: set[str]) -> int:
        score = 0
        for qt in query_tokens:
            if qt in plan_tokens:
                score += 2  # exact token hit ("sso", "enterprise", "499")
            elif any(qt in pt or pt in qt for pt in plan_tokens):
                score += 1  # partial/substring hit
        return score
