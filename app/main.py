"""FastAPI application factory + lifespan (the singleton wiring)."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import errors, middleware
from app.api.rate_limit import RateLimiter
from app.api.routes import catalog, chat, health, reviews
from app.catalog.keyword_search import KeywordCatalogSearch
from app.db.session import Database
from app.llm.anthropic_client import AnthropicClient
from app.logging_config import configure_logging
from app.reviews.notifier import NullNotifier
from app.settings import get_settings, validate_runtime_config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Singletons for the process lifetime. Schema is managed by Alembic (prod) or
    # create_all (tests) — the app does not migrate on boot.
    app.state.db = Database(settings.database_url)
    app.state.catalog = KeywordCatalogSearch.from_file(settings.catalog_path)
    app.state.llm = AnthropicClient(settings.anthropic_api_key)
    app.state.notifier = NullNotifier()
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.started_at = time.time()
    try:
        yield
    finally:
        await app.state.db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    validate_runtime_config(settings)  # refuse to boot with insecure production config
    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    middleware.register(app)
    errors.register(app)
    app.include_router(health.router)
    app.include_router(catalog.router)
    app.include_router(chat.router)
    app.include_router(reviews.router)
    return app


app = create_app()
