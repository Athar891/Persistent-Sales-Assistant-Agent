"""Typed, env-driven configuration with sane local defaults.

A single `Settings` object is the only place configuration is read. Everything
else receives values through dependency injection, never via `os.environ`.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- service metadata ---
    app_name: str = "persistent-sales-agent"
    version: str = "0.1.0"
    # "development" locally; set ENVIRONMENT=production on the host to turn the insecure
    # local defaults (open API, SQLite) into hard boot-time errors — see validate_runtime_config.
    environment: str = "development"

    # --- security ---
    # Shared secret gating /chat and /reviews. Empty locally → auth disabled (convenient for
    # dev/tests); REQUIRED in production (validate_runtime_config refuses to boot without it).
    api_key: str | None = None
    # Requests per minute per caller (keyed by API key, else client IP). 0 disables.
    rate_limit_per_minute: int = 60

    # --- persistence ---
    # Local default is file-backed SQLite; Railway injects a Postgres DATABASE_URL.
    # The scheme is normalised to an async driver in db/session.py.
    database_url: str = "sqlite+aiosqlite:///./sales_agent.db"

    # --- LLM (Anthropic) ---
    anthropic_api_key: str | None = None
    agent_model: str = "claude-sonnet-4-6"
    eval_model: str = "claude-haiku-4-5"
    summarizer_model: str = "claude-haiku-4-5"
    agent_max_tokens: int = 1024
    eval_max_tokens: int = 512
    summarizer_max_tokens: int = 512
    # Hard ceiling on agent tool-use round trips, so a misbehaving model cannot loop forever.
    max_agent_iterations: int = 6

    # --- memory ---
    recent_turns_window: int = 6  # most-recent turns kept verbatim in context
    summarize_after_turns: int = 12  # compress turns older than the window past this count

    # --- eval ---
    # Below this confidence a response is flagged and a human-review row is written.
    flag_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    # --- catalog ---
    catalog_path: str = "catalog.json"

    # --- logging ---
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"


def validate_runtime_config(settings: Settings) -> None:
    """Fail loud on insecure production configuration.

    The local defaults (no API key, SQLite) are deliberately convenient for dev — but each
    is a footgun in production: an open API with no key drains the LLM budget and leaks every
    user's history, and SQLite on an ephemeral container filesystem silently loses all
    'persistent' memory on the next redeploy. Rather than let those defaults reach production
    unnoticed, we refuse to start. Called once from create_app().
    """
    if not settings.is_production:
        return
    problems: list[str] = []
    if not settings.api_key:
        problems.append(
            "API_KEY must be set in production — without it /chat and /reviews are unauthenticated."
        )
    if settings.database_url.startswith("sqlite"):
        problems.append(
            "DATABASE_URL must be Postgres in production — SQLite is ephemeral on Railway and "
            "loses all stored memory on every redeploy."
        )
    if problems:
        raise RuntimeError(
            "Refusing to start with insecure production config:\n- " + "\n- ".join(problems)
        )


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton. Cached so env parsing happens exactly once."""
    return Settings()
