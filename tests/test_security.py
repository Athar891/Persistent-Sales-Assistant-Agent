"""Security layer: API-key auth, request bounds, rate limiting, and the prod-config guard.

The full-stack `harness` runs keyless on purpose (see conftest); here we stand up an app
with auth *enabled* to prove the gate actually rejects, and unit-test the limiter and the
startup guard directly so they stay deterministic.
"""

import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_settings_dep
from app.api.rate_limit import RateLimiter
from app.catalog.keyword_search import KeywordCatalogSearch
from app.db.session import Database
from app.main import create_app
from app.reviews.notifier import NullNotifier
from app.settings import Settings, validate_runtime_config
from tests.support import StubLLM

CATALOG = str(Path(__file__).resolve().parents[1] / "catalog.json")


@pytest.fixture
async def secured_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """A real ASGI app with auth turned on: protected routes require X-API-Key: secret."""
    app = create_app()
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/sec.db")
    await db.create_all()
    app.state.db = db
    app.state.catalog = KeywordCatalogSearch.from_file(CATALOG)
    app.state.llm = StubLLM()
    app.state.notifier = NullNotifier()
    app.state.started_at = time.time()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        api_key="secret", anthropic_api_key=None
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    await db.dispose()


async def test_chat_rejects_missing_or_wrong_key(secured_client: AsyncClient) -> None:
    r = await secured_client.post("/chat/acme", json={"message": "hi"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == 401

    wrong = await secured_client.post(
        "/chat/acme", json={"message": "hi"}, headers={"X-API-Key": "nope"}
    )
    assert wrong.status_code == 401


async def test_chat_accepts_the_correct_key(secured_client: AsyncClient) -> None:
    r = await secured_client.post(
        "/chat/acme", json={"message": "enterprise pricing?"}, headers={"X-API-Key": "secret"}
    )
    assert r.status_code == 200
    assert set(r.json()["data"]) == {"response", "eval", "tools_called", "session_id"}


async def test_reviews_is_gated_but_health_and_catalog_stay_open(
    secured_client: AsyncClient,
) -> None:
    assert (await secured_client.get("/reviews")).status_code == 401
    keyed = await secured_client.get("/reviews", headers={"X-API-Key": "secret"})
    assert keyed.status_code == 200
    # The platform health check and the public catalog must not require a key.
    assert (await secured_client.get("/health")).status_code == 200
    assert (await secured_client.get("/catalog")).status_code == 200


async def test_oversized_message_is_rejected(secured_client: AsyncClient) -> None:
    r = await secured_client.post(
        "/chat/acme", json={"message": "x" * 9000}, headers={"X-API-Key": "secret"}
    )
    assert r.status_code == 422


def test_rate_limiter_allows_then_blocks_then_recovers() -> None:
    rl = RateLimiter(2)
    assert rl.check("a", now=0.0) == (True, 0.0)
    assert rl.check("a", now=1.0)[0] is True
    allowed, retry_after = rl.check("a", now=2.0)  # third hit inside the 60s window
    assert allowed is False
    assert retry_after > 0
    assert rl.check("a", now=61.0)[0] is True  # window has rolled over


def test_rate_limiter_is_per_key_and_can_be_disabled() -> None:
    rl = RateLimiter(1)
    assert rl.check("a", now=0.0)[0] is True
    assert rl.check("b", now=0.0)[0] is True  # a different caller has its own budget
    assert rl.check("a", now=0.0)[0] is False
    assert RateLimiter(0).check("a", now=0.0) == (True, 0.0)  # 0 disables the limiter


def test_prod_config_guard_blocks_insecure_settings() -> None:
    sqlite_url = "sqlite+aiosqlite:///./x.db"
    pg_url = "postgresql+asyncpg://u:p@h:5432/db"

    with pytest.raises(RuntimeError):  # production without an API key
        validate_runtime_config(
            Settings(environment="production", api_key=None, database_url=pg_url)
        )
    with pytest.raises(RuntimeError):  # production on ephemeral SQLite
        validate_runtime_config(
            Settings(environment="production", api_key="k", database_url=sqlite_url)
        )
    # A correct production config — and any development config — must not raise.
    validate_runtime_config(Settings(environment="production", api_key="k", database_url=pg_url))
    validate_runtime_config(Settings(environment="development", database_url=sqlite_url))
