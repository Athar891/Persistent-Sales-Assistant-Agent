"""The catalog tool must *actually search* (rubric: tool use is real)."""

from pathlib import Path

import pytest

from app.catalog.keyword_search import KeywordCatalogSearch
from app.tools.search_catalog import SearchCatalogTool

CATALOG_PATH = str(Path(__file__).resolve().parents[1] / "catalog.json")


@pytest.fixture
def catalog() -> KeywordCatalogSearch:
    return KeywordCatalogSearch.from_file(CATALOG_PATH)


def test_loads_exactly_the_three_seeded_plans(catalog: KeywordCatalogSearch) -> None:
    assert [p.name for p in catalog.get_all()] == ["Starter", "Growth", "Enterprise"]


def test_ranks_enterprise_first_for_sso_query(catalog: KeywordCatalogSearch) -> None:
    results = catalog.search("does the enterprise plan include SSO?")
    assert results[0].name == "Enterprise"


def test_matches_on_a_price_token(catalog: KeywordCatalogSearch) -> None:
    results = catalog.search("$199")
    assert results[0].name == "Growth"


def test_matches_on_a_feature_token(catalog: KeywordCatalogSearch) -> None:
    results = catalog.search("which plan has webhooks")
    assert results[0].name == "Growth"


def test_empty_query_returns_full_catalog(catalog: KeywordCatalogSearch) -> None:
    assert len(catalog.search("")) == 3


def test_no_overlap_falls_back_to_full_catalog(catalog: KeywordCatalogSearch) -> None:
    assert len(catalog.search("xyzzy nonsense")) == 3


async def test_tool_formats_results_as_text(catalog: KeywordCatalogSearch) -> None:
    tool = SearchCatalogTool(catalog)
    out = await tool.run({"query": "enterprise sso"})
    assert "Enterprise — $499/mo" in out
    assert "SSO" in out
    assert tool.spec.name == "search_catalog"
    assert "query" in tool.spec.input_schema["properties"]
