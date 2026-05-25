"""Pydantic-Settings env loader for the SaferSkills API.

Every env var is read via this Settings class — never directly via os.environ.
See `.claude/rules/environment-config.md`.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:dev@localhost:5432/saferskills_dev",
        description="Async PostgreSQL DSN consumed by SQLAlchemy.",
    )

    # ── Observability (all optional at W1) ────────────────────────────────
    sentry_dsn: str | None = Field(default=None, description="Sentry DSN; None disables.")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, description="OTLP collector endpoint; None disables OTel export."
    )

    # ── Brand-independent project keys ────────────────────────────────────
    posthog_project_key: str | None = Field(default=None, description="Backend PostHog key (optional).")

    # ── Build identity ────────────────────────────────────────────────────
    git_sha: str = Field(default="unknown", description="Source commit SHA, injected at build time.")
    version: str = Field(default="0.0.0-foundation")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
