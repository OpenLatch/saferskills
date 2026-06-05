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

    # ── Connection budget (crash-resilience addendum §1) ───────────────────
    # Three pools open against one small Postgres per Machine: SQLAlchemy
    # (API + ingestion-task sessions), asyncpg (LISTEN/NOTIFY), and the
    # Procrastinate job-queue connector. The DB is a shared-cpu-1x:256MB box —
    # RAM, not the 300 max_connections, is the constraint (~5-10 MB per backend).
    # Lowered defaults keep idle footprint modest while still bursting on demand;
    # all env-configurable so they scale with prod RAM when real users arrive.
    db_pool_size: int = Field(
        default=5,
        ge=1,
        description="SQLAlchemy persistent pool size. API queries are short-lived.",
    )
    db_max_overflow: int = Field(
        default=10,
        ge=0,
        description="SQLAlchemy burst overflow above pool_size (released when idle).",
    )
    db_pool_timeout_s: float = Field(
        default=10.0,
        gt=0,
        description=(
            "Seconds a checkout waits for a free SQLAlchemy connection before "
            "raising TimeoutError — the back-pressure lever. Fail fast (503) "
            "under contention rather than hang every request until the worker "
            "frees a slot."
        ),
    )
    asyncpg_pool_max_size: int = Field(
        default=5,
        ge=1,
        description="asyncpg LISTEN/NOTIFY pool max size (SSE + scan worker).",
    )
    ingestion_queue_pool_max_size: int = Field(
        default=5,
        ge=1,
        description=(
            "Procrastinate job-queue connector pool max size — job poll + "
            "advisory locks + NOTIFY. Set explicitly; never inherit the library "
            "default. Task DB work uses the SQLAlchemy pool, not this one."
        ),
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
    saferskills_proxy_shared_secret: str | None = Field(
        default=None,
        description=(
            "Shared secret proving a request came from the trusted same-origin "
            "webapp proxy. When set, the per-IP rate limiter trusts the left-most "
            "X-Forwarded-For entry (the real visitor the proxy preserved) ONLY on "
            "requests carrying a matching `X-Proxy-Secret` header — so a direct "
            "caller to the public API cannot spoof XFF to dodge the cap. Unset "
            "(dev/test) → the raw TCP peer is used. The loopback exemption always "
            "keys on the real peer, never XFF. The webapp proxy reads the same "
            "value from `SAFERSKILLS_PROXY_SHARED_SECRET`. See security.md § "
            "Public-input handling #11 + scans.py::_rate_limit_ip."
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

    # ── Admin API (I-04 Phase C) ──────────────────────────────────────────
    saferskills_admin_key: str | None = Field(
        default=None,
        description=(
            "Shared secret gating the `POST/GET /api/v1/admin/*` endpoints via the "
            "`X-Admin-Key` header (D-04-28). Generated by `saferskills-admin auth "
            "gen-admin-key`; injected as a Fly secret. Unset + `ENV=development` → "
            "keyless local access (audits as `local-dev`); unset + staging/production "
            "→ every admin endpoint returns 403 (the gate fails closed). Replaced by "
            "SSO when auth lands (Track E)."
        ),
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

    # ── Auto-scan pipeline (durable bulk scan) ─────────────────────────────
    scan_autoscan_enabled: bool = Field(
        default=True,
        description=(
            "Enable the durable auto-scan pipeline (the reconciliation drainer + "
            "the merger on-ingest scan hook). Set false to pause all bulk scanning "
            "locally without touching the interactive POST /scans path."
        ),
    )
    scan_max_concurrency: int = Field(
        default=4,
        ge=1,
        description=(
            "Max concurrent durable `scan_capability_repo` jobs (in-body semaphore). "
            "INVARIANT: INGESTION_WORKER_CONCURRENCY + SCAN_MAX_CONCURRENCY must stay "
            "below DB_POOL_SIZE + DB_MAX_OVERFLOW (5 + 10 = 15) so the API keeps pool "
            "headroom. Asserted at startup (app/ingestion/worker.py)."
        ),
    )
    scan_reconcile_batch: int = Field(
        default=200,
        ge=1,
        description=(
            "Max repos the reconciliation drainer enqueues per tick (popularity-"
            "ordered). Bounds a 10k-burst so the box can't melt; the queueing_lock "
            "dedups against in-flight jobs."
        ),
    )
    scan_freshness_days: int = Field(
        default=30,
        ge=1,
        description=(
            "Periodic cheap re-check cadence — a repo whose last_checked_at is older "
            "than this is re-resolved (a 304 / unchanged ref just bumps last_checked_at, "
            "no scan)."
        ),
    )

    # ── Large-repo hybrid fetch (Git Trees + raw) ──────────────────────────
    # A monorepo / awesome-* collection blows the 25 MiB single-stream tarball
    # cap, failing the whole repo. Above this reported size the auto-scan path
    # skips the tarball and lists the tree (1 REST call, pinned to HEAD SHA) +
    # fetches only the ≤ 5 MiB blobs from raw.githubusercontent.com — the same
    # fileset the tarball keeps, so scores/snapshot/zip stay byte-identical.
    scan_large_repo_size_kb: int = Field(
        default=20480,  # ~20 MiB — margin under the 25 MiB compressed cap.
        ge=1,
        description=(
            "Reported repo size (KiB) above which the auto-scan pipeline routes to "
            "the Git Trees + raw fetch instead of the tarball. The tarball-cap "
            "fallback (TarballTooLargeError → trees) covers misclassification."
        ),
    )
    scan_trees_max_files: int = Field(
        default=4000,
        ge=1,
        description=(
            "Per-repo ceiling on raw blobs fetched via the Git Trees path. Beyond "
            "this, remaining blobs are skipped (graceful, not a failure) — bounds a "
            "many-small-file monorepo's raw-fetch fan-out."
        ),
    )
    scan_trees_max_total_bytes: int = Field(
        default=26_214_400,  # 25 MiB — parity with the tarball cap.
        ge=1,
        description=(
            "Per-repo total-bytes ceiling on the Git Trees raw-fetch path. Once hit, "
            "remaining blobs are skipped (graceful) — keeps the trees path's total "
            "footprint at tarball-cap parity."
        ),
    )
    scan_trees_fetch_concurrency: int = Field(
        default=8,
        ge=1,
        description=(
            "Max concurrent raw.githubusercontent.com blob fetches per repo on the "
            "Git Trees path (in-body semaphore)."
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

    # ── CLI Proof-of-Work scan-submit gate (I-05, D-05-30) ─────────────────
    # The install CLI can't solve a Turnstile CAPTCHA, so a stateless HMAC-signed
    # PoW challenge replaces Turnstile for CLI scan-submit. This secret is the
    # ONLY trust anchor of the stateless design — it MUST be a stable configured
    # value (identical across canary machines), never per-process random. None →
    # the `/cli-challenge` endpoint 503s and `verify_pow` rejects (the CLI then
    # falls back to Turnstile); a `model_validator` below hard-fails boot in
    # staging/production when it is unset, mirroring `turnstile_secret_key`.
    saferskills_cli_pow_secret: str | None = Field(
        default=None,
        description=(
            "HMAC-SHA256 secret signing the stateless CLI Proof-of-Work challenge "
            "(env `SAFERSKILLS_CLI_POW_SECRET`). None → /cli-challenge 503 + "
            "verify_pow rejects (dev/test/CI fall back to Turnstile). Required in "
            "staging/production (boot hard-fails otherwise)."
        ),
    )
    cli_pow_difficulty: int = Field(
        default=20,
        ge=1,
        le=28,
        description=(
            "Required leading-zero BITS on sha256(challenge||solution) for a valid "
            "CLI PoW. Capped at 28 so a hostile server can never make the CLI spin "
            "forever (the CLI mirrors this cap)."
        ),
    )
    cli_scan_submit_daily_limit: int = Field(
        default=100,
        ge=1,
        description=(
            "Max CLI scan submissions per IP per 24h on the PoW path (bucket "
            "`cli_scan_submit`, distinct from the Turnstile `scan_submit` bucket). "
            "Higher than the human limit because `scan --local` dedups by repo URL "
            "and submits one per installed capability."
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
            "db_pool_size + db_max_overflow (5 + 10 = 15) so the API keeps "
            "headroom (default 4 ⇒ ≥11 SQLAlchemy slots reserved for API "
            "traffic). Asserted at startup (crash-resilience addendum §1.5)."
        ),
    )
    ingestion_stalled_seconds: int = Field(
        default=14_400,  # 4h
        ge=60,
        description=(
            "Re-queue `doing` ingest-queue jobs (ingest_*/periodic) a worker "
            "abandoned on restart older than this (WS-7 `ingestion_stalled_retrier`). "
            "Generous default (4h) — comfortably above mcp_registry's worst-case "
            "full-feed cycle, so an in-flight long crawl is never mistaken for a "
            "stalled orphan. Sibling to the scan-queue's `scan_stalled_retrier`."
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
        if self.env in ("staging", "production") and self.saferskills_cli_pow_secret is None:
            raise ValueError(
                "SAFERSKILLS_CLI_POW_SECRET is required in staging/production — it is "
                "the only trust anchor of the stateless CLI Proof-of-Work gate (must "
                "be a stable Fly secret, identical across canary machines)."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
