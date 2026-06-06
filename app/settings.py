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


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton. Cached so env parsing happens exactly once."""
    return Settings()
