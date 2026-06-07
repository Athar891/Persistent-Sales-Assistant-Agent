"""Full-stack test harness: a real ASGI app over a temp file-backed SQLite DB, with the
Anthropic client swapped for a deterministic StubLLM. No key, no network, no cost.
"""

import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.security import require_api_key
from app.catalog.keyword_search import KeywordCatalogSearch
from app.db.session import Database
from app.main import create_app
from app.reviews.notifier import NullNotifier
from tests.support import Harness, StubLLM

CATALOG = str(Path(__file__).resolve().parents[1] / "catalog.json")


@pytest.fixture
async def harness(tmp_path: Path) -> AsyncIterator[Harness]:
    app = create_app()
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/api.db")
    await db.create_all()
    llm = StubLLM()

    # Mimic lifespan wiring with test doubles (ASGITransport doesn't run lifespan).
    app.state.db = db
    app.state.catalog = KeywordCatalogSearch.from_file(CATALOG)
    app.state.llm = llm
    app.state.notifier = NullNotifier()
    app.state.started_at = time.time()
    # These full-stack tests exercise behaviour, not auth — run them keyless.
    # Auth and rate limiting are covered directly in tests/test_security.py.
    app.dependency_overrides[require_api_key] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield Harness(client=client, llm=llm, db=db)
    await db.dispose()
