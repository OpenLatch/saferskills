"""Observability bootstrap — Sentry + OpenTelemetry.

W1 posture: every initialiser is a no-op when its env var is unset, so
`docker compose up` works against a fresh checkout without secrets.

W2 Phase A adds the Sentry breadcrumb scrubber from `app.observability.events`
(per `.claude/rules/telemetry.md` § Sentry). The scrubber drops any
breadcrumb whose data references rubric/, schemas/, fp-audit fixtures, or any
GitHub URL — prevents scanned-artifact content from leaking to Sentry.
"""

import structlog

from app.core.config import Settings
from app.core.log_redaction import install_log_redaction
from app.observability.events import scrub_sentry_breadcrumb, scrub_sentry_event

logger = structlog.get_logger(__name__)


def record_pool_timeout_breadcrumb(subsystem: str) -> None:
    """Sentry breadcrumb on a SQLAlchemy pool-checkout `TimeoutError`.

    The back-pressure event from the crash-resilience addendum (§1.3 / §2):
    when ingestion + API jointly exhaust the shared pool, the next checkout
    raises after `db_pool_timeout_s` instead of hanging. Tagging the breadcrumb
    `subsystem=ingestion|api` lets the post-mortem show who lost the race.
    No-op when Sentry is unconfigured (`add_breadcrumb` is safe pre-init).
    """
    try:
        import sentry_sdk  # type: ignore[import-not-found]

        sentry_sdk.add_breadcrumb(
            category="db_pool",
            message="SQLAlchemy pool checkout timed out (back-pressure)",
            level="warning",
            data={"subsystem": subsystem},
        )
    except Exception:  # observability must never break the app
        pass


async def init_observability(settings: Settings) -> None:
    # Always-on: redact the unlisted capability token from access/app logs
    # (D-UP-32(a)) — independent of Sentry/OTel being configured.
    install_log_redaction()

    if settings.sentry_dsn:
        try:
            import sentry_sdk  # type: ignore[import-not-found]
            from sentry_sdk.integrations.fastapi import (  # type: ignore[import-not-found]
                FastApiIntegration,
            )

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                integrations=[FastApiIntegration()],
                release=f"saferskills-api@{settings.version}+{settings.git_sha[:7]}",
                environment=settings.env,
                send_default_pii=False,
                traces_sample_rate=0.0,  # bumped per-environment from Fly secrets later
                before_breadcrumb=scrub_sentry_breadcrumb,
                before_send=scrub_sentry_event,  # pyright: ignore[reportArgumentType]
            )
            logger.info("sentry.initialised", env=settings.env)
        except Exception as exc:  # observability must never break the app
            logger.warning("sentry.init_failed", error=str(exc))

    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry import trace  # type: ignore[import-not-found]
            from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
            from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]

            resource = Resource.create(
                {"service.name": "saferskills-api", "service.version": settings.version}
            )
            trace.set_tracer_provider(TracerProvider(resource=resource))
            _init_db_pool_gauges(settings, resource)
            logger.info("otel.initialised")
        except Exception as exc:  # observability must never break the app
            logger.warning("otel.init_failed", error=str(exc))


def _init_db_pool_gauges(settings: Settings, resource: object) -> None:
    """Register OTel observable gauges on the shared SQLAlchemy pool.

    `ingestion.db_pool.in_use` / `.available` are the single most useful signal
    for "are we about to exhaust the pool the API and the ingestion worker share"
    (crash-resilience addendum §2) — a Grafana alert at `in_use > 12 / 15` fires
    *before* contention turns into hangs.

    Like the TracerProvider above, this wires the SDK provider + instruments but
    no metric reader/exporter — that dep is not installed at W1 and the addendum
    adds none. The callbacks register now and start being collected the moment a
    PeriodicExportingMetricReader + OTLP metric exporter are added in infra.
    """
    from opentelemetry import metrics  # type: ignore[import-not-found]
    from opentelemetry.metrics import (  # type: ignore[import-not-found]
        CallbackOptions,
        Observation,
    )
    from opentelemetry.sdk.metrics import MeterProvider  # type: ignore[import-not-found]

    from app.db.session import async_engine

    capacity = settings.db_pool_size + settings.db_max_overflow

    def _checked_out() -> int:
        # AsyncEngine wraps a sync (AsyncAdapted)QueuePool; .checkedout() is the
        # live in-use count. The base `Pool` type doesn't declare it, hence the
        # ignores — same SQLAlchemy typing gap the asyncpg pool init suppresses.
        return async_engine.sync_engine.pool.checkedout()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]

    def _in_use_cb(_options: CallbackOptions) -> list[Observation]:
        return [Observation(_checked_out())]

    def _available_cb(_options: CallbackOptions) -> list[Observation]:
        return [Observation(max(0, capacity - _checked_out()))]

    metrics.set_meter_provider(MeterProvider(resource=resource))  # pyright: ignore[reportArgumentType]
    meter = metrics.get_meter("saferskills.ingestion")
    meter.create_observable_gauge(
        "ingestion.db_pool.in_use",
        callbacks=[_in_use_cb],
        description="SQLAlchemy connections currently checked out of the shared pool.",
    )
    meter.create_observable_gauge(
        "ingestion.db_pool.available",
        callbacks=[_available_cb],
        description="Free SQLAlchemy slots remaining (pool_size + max_overflow - in_use).",
    )
