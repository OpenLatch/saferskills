"""Pydantic-Settings env loader for the SaferSkills API.

Every env var is read via this Settings class — never directly via os.environ.
See `.claude/rules/environment-config.md`.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Environment ────────────────────────────────────────────────────────
    env: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Environment tier — drives Sentry env tag and log format.",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Python logging level.",
    )

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:dev@localhost:5432/saferskills_dev",
        description="Async PostgreSQL DSN consumed by SQLAlchemy.",
    )

    # ── HTTP ───────────────────────────────────────────────────────────────
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:4321", "http://localhost:5173"],
        description="Comma-separated origin list. Source-of-truth for CORS middleware.",
    )
    public_base_url: str = Field(
        default="http://localhost:4321",
        description=(
            "Public origin of the webapp. Used to build capability `share_url`s "
            "(`/scans/r/<token>`) and upload `sources[].registryUrl`."
        ),
    )

    # ── Observability (all optional at W1) ────────────────────────────────
    sentry_dsn: str | None = Field(default=None, description="Sentry DSN; None disables.")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, description="OTLP collector endpoint; None disables OTel export."
    )

    # ── Brand-independent project keys ────────────────────────────────────
    posthog_project_key: str | None = Field(
        default=None, description="Backend PostHog key (optional)."
    )

    # ── Build identity ────────────────────────────────────────────────────
    git_sha: str = Field(
        default="unknown", description="Source commit SHA, injected at build time."
    )
    version: str = Field(default="0.0.0-foundation")

    # ── Scan engine identity ───────────────────────────────────────────────
    # Both versions are 7-40 char hex strings (git SHA prefix). At runtime they
    # fall back to `git_sha` if not explicitly set — the build pipeline stamps
    # them during the Docker image build (see Dockerfile ARG / ENV).
    rubric_version: str = Field(
        default="unknown",
        description="Git SHA of the rubric/ subtree at build time. Stamped on every scan + finding.",
    )
    engine_version: str = Field(
        default="unknown",
        description="Git SHA of the scan engine at build time. Stamped on every scan.",
    )

    # ── Rubric location ────────────────────────────────────────────────────
    # The rubric/ subtree lives at the monorepo root in source-checkout layout.
    # In Docker, the build context is `services/api/` so rubric/ is outside
    # the image; docker-compose mounts it as a read-only volume at /app/rubric.
    # Set this env var to override the auto-discovered path.
    rubric_dir: str | None = Field(
        default=None,
        description="Absolute path to the rubric/ directory. None → auto-discover.",
    )

    # ── GitHub fetch ───────────────────────────────────────────────────────
    github_token: str | None = Field(
        default=None,
        description=(
            "Optional GitHub PAT for tarball fetches. Without it the scan engine "
            "is subject to the 60 req/h anonymous rate limit; with it, 5,000 req/h."
        ),
    )

    # ── Rate limits ────────────────────────────────────────────────────────
    scan_submit_daily_limit: int = Field(
        default=10,
        ge=1,
        description="Maximum scan submissions per IP per 24h window (D-FE-11).",
    )
    artifact_download_daily_limit: int = Field(
        default=200,
        ge=1,
        description=(
            "Maximum stored-snapshot .zip downloads per IP per 24h window. "
            "Loopback callers (trusted local seeding) are exempt."
        ),
    )
    private_lookup_daily_limit: int = Field(
        default=60,
        ge=1,
        description=(
            "Maximum unlisted capability-URL (`/scans/r/{token}`) lookups per IP "
            "per 24h window. Denies an enumeration oracle (D-UP-15). Loopback exempt."
        ),
    )

    # ── Upload intake (I-3.5) ──────────────────────────────────────────────
    upload_max_bytes: int = Field(
        default=10_485_760,  # 10 MiB
        ge=1,
        description="Max accepted upload body size (streaming cap → 413).",
    )
    upload_extract_max_per_file_bytes: int = Field(
        default=5_242_880,  # 5 MiB
        ge=1,
        description="Max uncompressed bytes per file inside an uploaded .zip.",
    )
    upload_extract_max_total_bytes: int = Field(
        default=52_428_800,  # 50 MiB
        ge=1,
        description="Max total uncompressed bytes across an uploaded .zip.",
    )
    upload_extract_max_ratio: int = Field(
        default=100,
        ge=1,
        description="Max per-entry compression ratio (zip-bomb guard, incremental).",
    )
    upload_extract_max_entries: int = Field(
        default=1000,
        ge=1,
        description="Max file entries inside an uploaded .zip.",
    )
    upload_allowed_extensions: list[str] = Field(
        default=[
            ".zip",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".txt",
            ".js",
            ".ts",
            ".py",
            ".sh",
        ],
        description="Allowlist of accepted upload file extensions (else 415).",
    )
    unlisted_retention_days: int = Field(
        default=90,
        ge=1,
        description="Days an unlisted run is retained before the expiry sweep deletes it.",
    )
    upload_rescan_window_days: int = Field(
        default=90,
        ge=1,
        description="Window within which a public upload may be rescanned.",
    )
    sweep_interval_seconds: int = Field(
        default=3600,
        ge=60,
        description="Interval between unlisted-run expiry sweeps (in-process loop).",
    )

    # ── Vendor right-of-reply ──────────────────────────────────────────────
    # HS256 signing key for the short-lived `ss_vendor_session` JWT minted on
    # successful `.saferskills/verify.txt` redemption. The webapp stores the
    # JWT in an HttpOnly cookie and forwards it back as a Bearer token; the API
    # is the sole verifier (the secret never leaves the backend). Rotate
    # quarterly — rotation invalidates in-flight 15-minute sessions, no more.
    vendor_session_secret: str = Field(
        default="dev-insecure-vendor-session-secret-change-me",
        description="HS256 key for vendor session JWTs. MUST be overridden in prod.",
    )

    # ── Human-verification (Cloudflare Turnstile) ──────────────────────────
    # Server-side `siteverify` secret for the scan-submit CAPTCHA gate. None →
    # the gate is bypassed (dev/test/CI). The `model_validator` below forbids a
    # missing secret in staging/production so a real deploy never runs open.
    # In non-prod, use Cloudflare's always-pass test secret `1x0000000000000000000000000000000AA`.
    turnstile_secret_key: str | None = Field(
        default=None,
        description=(
            "Cloudflare Turnstile siteverify secret for the scan-submit human "
            "gate. None → bypass (dev/test only — forbidden in staging/prod)."
        ),
    )

    # ── Ingestion (I-04 Phase A) ───────────────────────────────────────────
    ingestion_worker_enabled: bool = Field(
        default=True,
        description=(
            "Start the in-process Procrastinate ingestion worker in the FastAPI "
            "lifespan (advisory lock 0x5AFE5C13). Set false in some test contexts; "
            "live external cadence still needs the GitHub App creds below."
        ),
    )
    ingestion_worker_concurrency: int = Field(
        default=4,
        ge=1,
        description=(
            "Procrastinate worker concurrency. INVARIANT: must stay below "
            "db pool_size + max_overflow (10 + 20 = 30) so the API keeps headroom "
            "(crash-resilience addendum §1)."
        ),
    )
    github_app_id: str | None = Field(
        default=None, description="GitHub App `saferskills-ingest` numeric App ID (outbox 01)."
    )
    github_app_private_key: str | None = Field(
        default=None,
        description="GitHub App PEM private key (RS256). Multi-line; base64 in a Fly secret.",
    )
    github_app_installation_id: str | None = Field(
        default=None, description="GitHub App installation id (numeric)."
    )
    github_webhook_secret: str | None = Field(
        default=None,
        description="HMAC-SHA256 secret for X-Hub-Signature-256 verification on POST /webhooks/github.",
    )
    hishel_db_path: str = Field(
        default="/data/.hishel.db",
        description="Hishel RFC-9111 SQLite cache path (Fly volume mount, outbox 04).",
    )
    hishel_max_size_bytes: int = Field(
        default=524_288_000,  # 500 MiB
        ge=1,
        description="Hishel cache LRU size cap.",
    )
    hishel_github_ttl_seconds: int = Field(
        default=86_400,  # 24h
        ge=1,
        description="Hishel cache TTL for api.github.com / raw.githubusercontent.com.",
    )
    hishel_aggregator_ttl_seconds: int = Field(
        default=3_600,  # 1h
        ge=1,
        description="Hishel cache TTL for scraped aggregator hosts (Phase B).",
    )
    ingestion_source_blocklist: list[str] = Field(
        default=[],
        description="Comma-separated source names disabled in this env (e.g. 'mcp_so').",
    )
    ingestion_github_code_search_enabled: bool = Field(
        default=False,
        description=(
            "Enable the github_topics code-search discovery pass (D-04-35). Default off "
            "in Phase A1; flipped on in the fast-follow once Search-API budget is confirmed."
        ),
    )
    slack_alerts_webhook_url: str | None = Field(
        default=None,
        description="Slack incoming-webhook URL for #saferskills-alerts (Phase C; outbox 03).",
    )

    @field_validator("ingestion_source_blocklist", mode="before")
    @classmethod
    def _parse_blocklist(cls, value: object) -> object:
        if isinstance(value, str):
            return [s.strip() for s in value.split(",") if s.strip()]
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("upload_allowed_extensions", mode="before")
    @classmethod
    def _parse_allowed_extensions(cls, value: object) -> object:
        """Parse a comma-separated env string into a normalized extension list.

        Each entry is lowercased and dot-prefixed (`md` and `.MD` both → `.md`).
        """
        if isinstance(value, str):
            parts = [p.strip().lower() for p in value.split(",") if p.strip()]
            return [p if p.startswith(".") else f".{p}" for p in parts]
        return value

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_db_scheme(cls, value: str) -> str:
        """Coerce the DSN to the async driver SQLAlchemy 2.x requires.

        Managed Postgres providers — including Fly's `postgres attach` — hand
        out `postgres://…` DSNs, but SQLAlchemy 2.x dropped the legacy
        `postgres` dialect alias, so `create_async_engine` crashes boot with
        `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres`.
        Normalize a bare `postgres://` / `postgresql://` DSN to the
        `postgresql+asyncpg://` form every consumer here expects
        (`db/session.py`, `migrations/env.py`; `db_pool.py` strips the driver
        hint back off for raw asyncpg). An explicit `+driver` is left intact.
        """
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        return value

    @model_validator(mode="after")
    def _require_turnstile_secret_in_prod(self) -> Settings:
        """Hard-fail boot when the Turnstile secret is missing in staging/prod.

        The silent-bypass behaviour of `verify_turnstile` (no secret → accept)
        is only safe in dev/test. Mirrors the `vendor_session_secret` "MUST be
        overridden in prod" intent — a deploy that forgot the secret must crash
        at startup, never run the human gate open.
        """
        if self.env in ("staging", "production") and self.turnstile_secret_key is None:
            raise ValueError(
                "TURNSTILE_SECRET_KEY is required in staging/production "
                "(set Cloudflare's test secret in non-prod CI)."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
