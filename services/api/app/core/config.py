"""Pydantic-Settings env loader for the SaferSkills API.

Every env var is read via this Settings class — never directly via os.environ.
See `.claude/rules/environment-config.md`.
"""

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _coerce_sslmode_to_ssl(value: str) -> str:
    """Rename a libpq `sslmode` query param to asyncpg's `ssl`.

    Managed Postgres DSNs (Fly Managed Postgres, Supabase, Neon, …) carry a
    `?sslmode=require` query param. libpq + psycopg understand it, but
    SQLAlchemy's **asyncpg** dialect forwards unrecognized query params straight
    to `asyncpg.connect()` as kwargs, and asyncpg has no `sslmode` kwarg — boot
    dies with `connect() got an unexpected keyword argument 'sslmode'` and the
    API drops into degraded mode (503 on every route but `/api/v1/health`).
    asyncpg's equivalent is `ssl`, which both the SQLAlchemy dialect and raw
    asyncpg accept with the same libpq value strings (`disable` / `require` /
    `verify-full` / …). Rename the key, preserve the value; if an explicit `ssl`
    is already present it wins and the `sslmode` alias is dropped.
    """
    if "sslmode=" not in value:
        return value
    parts = urlsplit(value)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    has_ssl = any(key == "ssl" for key, _ in pairs)
    rebuilt: list[tuple[str, str]] = []
    for key, val in pairs:
        if key == "sslmode":
            if has_ssl:
                continue  # explicit ssl wins — drop the libpq alias
            rebuilt.append(("ssl", val))
        else:
            rebuilt.append((key, val))
    return urlunsplit(parts._replace(query=urlencode(rebuilt)))


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
    def _normalize_db_dsn(cls, value: str) -> str:
        """Coerce the DSN to the async form every consumer here expects.

        Two managed-Postgres quirks crash boot otherwise:

        1. **Scheme** — providers (including Fly's `postgres attach`) hand out
           `postgres://…` / `postgresql://…` DSNs, but SQLAlchemy 2.x dropped
           the legacy `postgres` alias and needs an explicit `+asyncpg` driver,
           or `create_async_engine` raises `NoSuchModuleError`. Every consumer
           expects the `postgresql+asyncpg://` form (`db/session.py`,
           `migrations/env.py`; `db_pool.py` strips the hint back off for raw
           asyncpg).
        2. **SSL** — a `?sslmode=…` query param is libpq-only; the asyncpg
           dialect forwards it as a bad `connect()` kwarg. `_coerce_sslmode_to_ssl`
           renames it to `ssl`.

        An explicit `+driver` is left intact.
        """
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        return _coerce_sslmode_to_ssl(value)

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
