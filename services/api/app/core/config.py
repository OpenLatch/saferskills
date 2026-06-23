"""Pydantic-Settings env loader for the SaferSkills API.

Every env var is read via this Settings class — never directly via os.environ.
See `.claude/rules/environment-config.md`.
"""

import base64
import binascii
from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The placeholder vendor-session signing key. It ships in the open-source repo, so a
# deploy that kept it would mint forgeable verified-vendor sessions — the prod boot
# guard below rejects it (and any <32-byte key) in staging/production.
_DEV_INSECURE_VENDOR_SESSION_SECRET = "dev-insecure-vendor-session-secret-change-me"


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


def coerce_ssl_to_sslmode(value: str) -> str:
    """Rename asyncpg's `ssl` query param back to libpq's `sslmode`.

    Public (unlike its `_coerce_sslmode_to_ssl` inverse) because it is consumed
    cross-module by `app.ingestion._libpq_conninfo`. The exact inverse of
    `_coerce_sslmode_to_ssl`. `settings.database_url` is the
    asyncpg-flavoured DSN (it carries `?ssl=disable`), but Procrastinate's psycopg3
    `PsycopgConnector` speaks **libpq**, which rejects `ssl` outright
    (`invalid URI query parameter: "ssl"`) — it wants `sslmode`. The value strings
    are identical (`disable` / `require` / `verify-full` / …), so only the key is
    renamed. If an explicit `sslmode` is already present it wins and the `ssl`
    alias is dropped. (`"ssl="` is not a substring of `"sslmode="`, so a DSN that
    only carries `sslmode` is left untouched.)
    """
    if "ssl=" not in value:
        return value
    parts = urlsplit(value)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    has_sslmode = any(key == "sslmode" for key, _ in pairs)
    rebuilt: list[tuple[str, str]] = []
    for key, val in pairs:
        if key == "ssl":
            if has_sslmode:
                continue  # explicit sslmode wins — drop the asyncpg alias
            rebuilt.append(("sslmode", val))
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

    # ── Connection budget ──────────────────────────────────────────────────
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
    db_statement_timeout_s: int = Field(
        default=30,
        ge=0,
        description=(
            "Postgres per-statement timeout (seconds) on the shared SQLAlchemy "
            "engine. A query exceeding it is ABORTED by Postgres (SQLSTATE 57014 "
            "→ a bounded 503), freeing the pooled connection instead of letting "
            "one slow query hang every request behind the pool-checkout timeout. "
            "Also drives idle_in_transaction_session_timeout (same value). 0 "
            "disables. PER-STATEMENT, so the chunked bulk-scan writes (each fast) "
            "are safe; alembic runs on a SEPARATE engine (migrations/env.py) and "
            "is unaffected. The migration + procrastinate-schema advisory-lock "
            "holders and the CONCURRENTLY materialized-view refresh are explicitly "
            "exempted. Tighten per tier in fly.*.toml [env] (the API can run "
            "tighter than the bulk worker)."
        ),
    )
    db_command_timeout_s: float = Field(
        default=35.0,
        ge=0,
        description=(
            "asyncpg CLIENT-side command timeout (seconds) on the shared "
            "SQLAlchemy engine. This is the ONLY bound that catches a HALF-OPEN "
            "connection (the socket is dead but never got a TCP reset, so a query "
            "writes into it and waits forever): statement_timeout is server-side "
            "(the server never receives the query → never cancels) and pool_timeout "
            "bounds only the slot wait, so without this a dead pooled connection "
            "hangs every request indefinitely (the staging incident). Set ABOVE "
            "DB_STATEMENT_TIMEOUT_S (default 35 > 30) so a legit slow query gets "
            "the clean server-side 503 first and this only ever fires for a truly "
            "dead connection. A fired timeout surfaces as a builtin TimeoutError → "
            "`app/main.py` maps it to a bounded 503 and SQLAlchemy discards the "
            "connection (pool_pre_ping + pool_recycle then re-establish). 0 disables."
        ),
    )
    db_pool_recycle_s: int = Field(
        default=1800,
        ge=0,
        description=(
            "Max age (seconds) of a pooled SQLAlchemy connection before it is "
            "discarded + re-established on next checkout (SQLAlchemy `pool_recycle`). "
            "The PROACTIVE half of half-open-connection defence (asyncpg exposes no "
            "TCP-keepalive knob): a connection silently dropped by a proxy / 6PN / "
            "PG-side close can't outlive this window, so it is refreshed before it "
            "can hang a request. Pairs with pool_pre_ping (liveness check on "
            "checkout, now fail-fast thanks to db_command_timeout_s) and "
            "db_command_timeout_s (the reactive bound). 0 disables recycling."
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
        default="http://localhost:5173",
        description=(
            "Public origin of the webapp. Used to build capability `share_url`s "
            "(`/scans/r/<token>`), the public report `report_url` (`/scans/<run_id>`), "
            "and upload `sources[].registryUrl`. The dev default matches the webapp "
            "dev/preview server (`astro dev --port 5173`); set per-env in production."
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

    # ── SEO / discovery ──────────────────────────────────────────────────────
    saferskills_site_origin: str = Field(
        default="https://saferskills.ai",
        description=(
            "Canonical public origin of the SaferSkills site, used to build "
            "absolute `<loc>` URLs in the generated sitemap and the URL set sent "
            "to IndexNow. Distinct from `public_base_url` (the webapp dev/preview "
            "origin used for capability share_urls): this is always the real "
            "saferskills.ai apex so crawler-facing URLs are clean regardless of "
            "the internal proxy origin. See `.claude/rules/environment-config.md`."
        ),
    )
    saferskills_indexnow_key: str | None = Field(
        default=None,
        description=(
            "IndexNow API key. Pings Bing/Yandex/DuckDuckGo/Seznam/Naver/Yep "
            "(NOT Google) on new public, real-data pages. Unset (dev/test/CI) → "
            "the submitter is a no-op. The key file is served statically at "
            "`webapp/public/<KEY>.txt` (provisioned out-of-band)."
        ),
    )
    saferskills_indexnow_key_location: str | None = Field(
        default=None,
        description=(
            "Absolute URL of the IndexNow key verification file "
            "(`https://saferskills.ai/<KEY>.txt`). Sent as `keyLocation` in the "
            "IndexNow POST body. Unset → omitted (the engines then look for the "
            "key at the host root)."
        ),
    )

    # ── Observability (all optional) ──────────────────────────────────────
    sentry_dsn: str | None = Field(default=None, description="Sentry DSN; None disables.")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, description="OTLP collector endpoint; None disables OTel export."
    )

    # ── Brand-independent project keys ────────────────────────────────────
    posthog_project_key: str | None = Field(
        default=None,
        description=(
            "Backend PostHog project (write) key. None disables server-side "
            "PostHog dispatch — every emit_* helper degrades to structlog-only."
        ),
    )
    posthog_host: str = Field(
        default="https://eu.i.posthog.com",
        description="PostHog ingestion host (EU region). Shared OpenLatch-portfolio project.",
    )
    posthog_server_key: str | None = Field(
        default=None,
        description=(
            "PostHog personal API key (`phx_…`) enabling LOCAL feature-flag "
            "evaluation in `app.core.feature_flags`. None → flags fall back to "
            "remote `/decide` via the project key, or to the supplied default."
        ),
    )

    # ── Admin API ──────────────────────────────────────────────────────────
    saferskills_admin_key: str | None = Field(
        default=None,
        description=(
            "Shared secret gating the `POST/GET /api/v1/admin/*` endpoints via the "
            "`X-Admin-Key` header. Generated by `saferskills-admin auth "
            "gen-admin-key`; injected as a Fly secret. Unset + `ENV=development` → "
            "keyless local access (audits as `local-dev`); unset + staging/production "
            "→ every admin endpoint returns 403 (the gate fails closed). Replaced by "
            "SSO when auth lands."
        ),
    )

    # ── Build identity ────────────────────────────────────────────────────
    git_sha: str = Field(
        default="unknown", description="Source commit SHA, injected at build time."
    )
    version: str = Field(default="0.0.0-foundation")
    fly_machine_id: str | None = Field(
        default=None,
        description=(
            "Fly Machine id (platform-injected `FLY_MACHINE_ID`). Used as the OTel "
            "`service.instance.id` so each Machine is distinguishable in Tempo; "
            "falls back to the hostname when unset (local/dev)."
        ),
    )

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
    scan_reconcile_max_backlog: int = Field(
        default=500,
        ge=1,
        description=(
            "Back-pressure ceiling on the `scan`-queue backlog (count of `todo` "
            "scan_capability_repo jobs in procrastinate_jobs). When the reconciliation "
            "drainer (`auto_scan_reconcile`) sees a backlog at or above this, it SKIPS "
            "the tick — never piling more onto a worker already behind, the missing "
            "back-pressure that lets the shared-Postgres staging box saturate. The "
            "10-min cadence re-checks next tick."
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
    scan_max_index_files: int = Field(
        default=4000,
        ge=1,
        description=(
            "Per-repo ceiling on files admitted to the in-memory scan file index, on "
            "EVERY fetch path (tarball walk + Git Trees). Beyond this, remaining "
            "files are skipped (graceful, not a failure; recorded on the report) — "
            "bounds a many-small-file monorepo's footprint."
        ),
    )
    scan_max_index_total_bytes: int = Field(
        default=26_214_400,  # 25 MiB — the per-repo in-memory index budget.
        ge=1,
        description=(
            "Per-repo total-bytes ceiling on the in-memory scan file index, on EVERY "
            "fetch path (tarball walk + Git Trees). Once hit, remaining files are "
            "skipped (graceful; recorded on the report). The 25 MiB tarball cap is "
            "COMPRESSED-stream only — this is the bound on what actually sits in RAM."
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
        description="Maximum scan submissions per IP per 24h window.",
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
            "per 24h window. Denies an enumeration oracle. Loopback exempt."
        ),
    )

    # ── Upload intake ──────────────────────────────────────────────────────
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
        default=_DEV_INSECURE_VENDOR_SESSION_SECRET,
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

    # ── CLI Proof-of-Work scan-submit gate ─────────────────────────────────
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

    # ── Agent Scan ──────────────────────────────────────────────────────────
    # The behavioral agent scan signs each per-run pack (Ed25519) and derives
    # per-run rotating canaries from a master key. Both secrets are the trust
    # anchors of the lean crypto posture — they MUST be stable
    # configured values (identical across canary machines), never per-process
    # random. Unset → packs serve unsigned (`manual-bootstrap`) + canaries fall
    # back to a dev key; the `model_validator` below hard-fails boot in
    # staging/production when either is missing (mirrors the Turnstile/PoW guard).
    saferskills_agent_master_key: str | None = Field(
        default=None,
        description=(
            "Base64 master key (≥32 bytes) — the HKDF source for per-run canary "
            "seeds AND the one-time run/submit token HMAC key (env "
            "`SAFERSKILLS_AGENT_MASTER_KEY`). Server-only, never shipped. Required "
            "in staging/production (boot hard-fails otherwise)."
        ),
    )
    saferskills_pack_signing_key: str | None = Field(
        default=None,
        description=(
            "Base64 32-byte Ed25519 seed signing each served agent pack (env "
            "`SAFERSKILLS_PACK_SIGNING_KEY`). The single launch key; its public "
            "half is served at `GET /api/v1/agent-pack/keys` + baked into the CLI. "
            "Unset → packs serve unsigned (dev/test). Required in "
            "staging/production (boot hard-fails otherwise)."
        ),
    )
    agent_scan_submit_daily_limit: int = Field(
        default=20,
        ge=1,
        description=(
            "Max agent-scan submissions per IP per 24h (bucket `agent_scan_submit`, "
            "distinct from the URL/CLI scan buckets). Loopback exempt."
        ),
    )
    agent_run_token_ttl_seconds: int = Field(
        default=1800,
        ge=60,
        description=(
            "TTL of the one-time agent run/submit token (30 min — covers a ~2-3 "
            "min scan + slack). Bounds the single-use ledger window."
        ),
    )
    unlisted_agent_retention_days: int = Field(
        default=90,
        ge=1,
        description=(
            "TTL (days) for an unlisted Agent Report — sets `agent_runs.expires_at`; "
            "swept by `app/core/sweeps.py`."
        ),
    )
    ipinfo_lite_db_path: str = Field(
        default="/app/data/ipinfo-lite.mmdb",
        description=(
            "Baked-image path of the IPinfo Lite `.mmdb` for company-level IP→ASN "
            "telemetry. Static asset, single-store rule intact."
        ),
    )
    agent_corpus_gate_n: int = Field(
        default=500,
        ge=1,
        description=(
            "Minimum public agent-scan corpus size before the `/agents` directory "
            "publishes its headline aggregate stat (% carrying a critical finding). "
            "Below it the stat is gated ('collecting') to avoid misleading-at-small-N. "
            "Founder-overridable without a code change."
        ),
    )

    # ── Ingestion ────────────────────────────────────────────────────────────
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
            "traffic). Asserted at startup."
        ),
    )
    ingestion_worker_shutdown_timeout_s: float = Field(
        default=5.0,
        gt=0,
        description=(
            "Seconds the Procrastinate worker waits for in-flight jobs to finish "
            "on shutdown before ABORTING them (passed as `shutdown_graceful_timeout` "
            "to `run_worker_async`). Without it the worker waits forever for an "
            "in-flight job (e.g. a multi-minute mcp_registry full-feed cycle), so a "
            "`--reload` mid-ingestion hangs the process. Aborted jobs are durable — "
            "Procrastinate re-queues SHUTDOWN-aborted jobs + batches commit "
            "incrementally — so at most the current 25-item batch is re-run."
        ),
    )
    worker_watchdog_timeout_s: float = Field(
        default=900.0,  # 15 min
        ge=0,
        description=(
            "Standalone-worker liveness watchdog (app/worker_main.py). An OS "
            "thread (independent of the asyncio loop) hard-exits the process — "
            "letting Fly's `restart=always` reboot the Machine — when the event "
            "loop stops refreshing its heartbeat for this many seconds. A deployed "
            "worker has no HTTP health check and `[restart] policy` only fires on "
            "process exit, so a WEDGED loop (observed: 46 min of total silence, "
            "recovered only by a manual restart) is otherwise unrecoverable. "
            "Generous default (15 min) so a legitimately long in-loop operation "
            "never trips it — only a true hang does. `0` disables the watchdog."
        ),
    )
    ingestion_stalled_seconds: int = Field(
        default=14_400,  # 4h
        ge=60,
        description=(
            "Re-queue `doing` ingest-queue jobs (ingest_*/periodic) a worker "
            "abandoned on restart older than this (the `ingestion_stalled_retrier`). "
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
        description="GitHub App PEM private key (RS256). Accepts a raw multi-line PEM "
        "or a base64-encoded PEM (decoded at load by `_normalize_github_app_private_key`). "
        "Prefer the single-line `GITHUB_APP_PRIVATE_KEY_B64` secret in deployment.",
    )
    github_app_private_key_b64: str | None = Field(
        default=None,
        description="Base64-encoded GitHub App PEM (Fly secret GITHUB_APP_PRIVATE_KEY_B64). "
        "Decoded into github_app_private_key at load when the raw key is unset — a "
        "single-line secret avoids multi-line Fly-secret quoting.",
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
        description="Hishel cache TTL for scraped aggregator hosts.",
    )
    ingestion_source_blocklist: list[str] = Field(
        default=[],
        description="Comma-separated source names disabled in this env (e.g. 'mcp_so').",
    )
    ingestion_github_code_search_enabled: bool = Field(
        default=False,
        description=(
            "Enable the github_topics code-search discovery pass. Default off "
            "initially; flipped on in a fast-follow once Search-API budget is confirmed."
        ),
    )
    slack_alerts_webhook_url: str | None = Field(
        default=None,
        description="Slack incoming-webhook URL for #saferskills-alerts (ingestion failure alerts).",
    )
    slack_invite_url: str | None = Field(
        default=None,
        description=(
            "Public Slack shared-invite URL for the shared openlatch-community "
            "workspace — the GET /api/v1/community/slack/redirect target. A "
            "Slack-native never-expire link (public, NOT a secret). Unset → the "
            "redirect 503s and the health-check loop no-ops."
        ),
    )
    slack_invite_health_interval_seconds: int = Field(
        default=21_600,  # 6h
        ge=60,
        description=(
            "Interval (s) of the in-process Slack-invite health probe loop "
            "(advisory lock 0x5AFE5C14). On a broken invite it alerts via "
            "SLACK_ALERTS_WEBHOOK_URL + Sentry."
        ),
    )

    @field_validator("slack_invite_url", mode="after")
    @classmethod
    def _validate_slack_invite_url(cls, value: str | None) -> str | None:
        """Restrict the invite URL to an `https://*.slack.com` host.

        The redirect endpoint 302s to whatever this holds, so an env misconfig
        (or a typo'd domain) must never become an open redirect. Host-based, so
        it accepts `join.slack.com/t/<ws>/shared_invite/zt-…`.

        A blank value (the `.env.example` placeholder / docker-compose
        `${SLACK_INVITE_URL:-}` empty default) normalizes to `None` — the same
        "effectively unset" behaviour as the other optional URL fields, so an
        unconfigured deploy boots (redirect 503s, health loop no-ops) instead of
        crashing on `urlsplit("")`.
        """
        if value is None or not value.strip():
            return None
        value = value.strip()
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or not (host == "slack.com" or host.endswith(".slack.com")):
            raise ValueError(
                "SLACK_INVITE_URL must be an https://*.slack.com URL (e.g. "
                "https://join.slack.com/t/openlatch-community/shared_invite/zt-…)."
            )
        return value

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
        if self.env in ("staging", "production") and self.saferskills_agent_master_key is None:
            raise ValueError(
                "SAFERSKILLS_AGENT_MASTER_KEY is required in staging/production — it "
                "is the HKDF trust anchor for per-run agent-scan canaries + run "
                "tokens (must be a stable Fly secret, identical across canary machines)."
            )
        if self.env in ("staging", "production") and self.saferskills_pack_signing_key is None:
            raise ValueError(
                "SAFERSKILLS_PACK_SIGNING_KEY is required in staging/production — it "
                "signs every served agent pack; unset would serve unsigned packs the "
                "baked CLI pubkey cannot verify (must be a stable Fly secret)."
            )
        if self.env in ("staging", "production") and (
            self.vendor_session_secret == _DEV_INSECURE_VENDOR_SESSION_SECRET
            or len(self.vendor_session_secret) < 32
        ):
            raise ValueError(
                "VENDOR_SESSION_SECRET is required in staging/production — it signs the "
                "vendor right-of-reply session JWT (app/routers/vendor.py). The dev "
                "default is public in the open-source repo, so a deploy that kept it "
                "would mint forgeable verified-vendor sessions (set a stable 32+ byte "
                "Fly secret, identical across canary machines)."
            )
        return self

    @model_validator(mode="after")
    def _normalize_github_app_private_key(self) -> Settings:
        """Resolve the GitHub App private key to a raw PEM the JWT signer can use.

        The key is stored **base64-encoded** in a Fly secret (single-line — multi-line
        PEM secrets are awkward to set and quote), under `GITHUB_APP_PRIVATE_KEY_B64`.
        The JWT signer (`app/core/github_app_token.py`) feeds the value straight into
        `jwt.encode(..., algorithm="RS256")`, which needs a raw PEM — so decode here.

        Accepts, in priority order, and always lands a raw PEM (or None) in
        `github_app_private_key`:
          1. a raw PEM already in `github_app_private_key` (kept as-is);
          2. a base64 value in `github_app_private_key` (decoded);
          3. the dedicated `github_app_private_key_b64` secret (decoded).
        A value that is neither a PEM nor valid base64-of-a-PEM is reset to None so
        token minting fails *gracefully* (anonymous fallback) rather than 500-ing
        every GitHub fetch. Without this, the `_B64` secret was silently never read
        and every API + worker GitHub call ran anonymous (60 req/h).
        """
        raw = self.github_app_private_key
        if raw and "-----BEGIN" in raw:
            return self  # already a usable PEM
        candidate = (raw or self.github_app_private_key_b64 or "").strip()
        if not candidate:
            self.github_app_private_key = None
            return self
        try:
            decoded = base64.b64decode(candidate).decode("utf-8")
        except binascii.Error, ValueError, UnicodeDecodeError:
            decoded = ""
        self.github_app_private_key = decoded if "-----BEGIN" in decoded else None
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
