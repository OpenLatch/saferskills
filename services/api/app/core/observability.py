"""Observability bootstrap — structured logging + Sentry + OpenTelemetry + PostHog.

Posture: every initialiser is a no-op when its key/endpoint is unset, so
`docker compose up` works against a fresh checkout without secrets. Observability
must NEVER break the app — every init is wrapped and degrades on failure.

Legs:
  - **Logging** (`app.core.logging`): structlog JSON → stdout, with
    `inject_trace_context` for Loki↔Tempo correlation. Configured FIRST.
  - **Sentry**: errors only, with the breadcrumb + event scrubbers from
    `app.observability.events` (drops scanned-artifact content; redacts the
    unlisted capability token).
  - **OpenTelemetry**: traces exported via OTLP/HTTP to the shared Grafana Vector
    (`OTEL_EXPORTER_OTLP_ENDPOINT`). Metrics are deferred — the pool gauges stay
    registered (harmless) but no metric reader/exporter is wired yet.
  - **PostHog**: server-side product analytics (the `emit_*` allowlist), tagged
    `product = "saferskills"`. Client lives in `app.observability.events`.
"""

import socket

import structlog

from app.core.config import Settings
from app.core.log_redaction import install_log_redaction
from app.core.logging import configure_logging
from app.observability import events
from app.observability.events import scrub_sentry_breadcrumb, scrub_sentry_event

logger = structlog.get_logger(__name__)


def record_pool_timeout_breadcrumb(subsystem: str) -> None:
    """Sentry breadcrumb on a SQLAlchemy pool-checkout `TimeoutError`.

    The back-pressure event: when ingestion + API jointly exhaust the shared
    pool, the next checkout
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
    # Logging first — so every subsequent init line is structured JSON on stdout.
    configure_logging(settings.log_level)
    # Always-on: redact the unlisted capability token from access/app logs
    # — independent of Sentry/OTel being configured.
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
            _init_otel(settings)
            logger.info("otel.initialised", endpoint=settings.otel_exporter_otlp_endpoint)
        except Exception as exc:  # observability must never break the app
            logger.warning("otel.init_failed", error=str(exc))

    # Server-side PostHog (no-op when the project key is unset).
    events.init_posthog(
        project_key=settings.posthog_project_key,
        host=settings.posthog_host,
        server_key=settings.posthog_server_key,
    )


def instrument_app(app: object) -> None:
    """Attach the OTel auto-instrumentors (FastAPI routes, SQLAlchemy queries,
    outbound HTTPX). No-op-safe: only called when an OTLP endpoint is configured,
    and wrapped by the caller. Health/ready/metrics routes are excluded so probe
    traffic doesn't flood Tempo with empty spans.
    """
    from opentelemetry.instrumentation.fastapi import (  # type: ignore[import-not-found]
        FastAPIInstrumentor,
    )
    from opentelemetry.instrumentation.httpx import (  # type: ignore[import-not-found]
        HTTPXClientInstrumentor,
    )
    from opentelemetry.instrumentation.sqlalchemy import (  # type: ignore[import-not-found]
        SQLAlchemyInstrumentor,
    )

    from app.db.session import async_engine

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,metrics")  # pyright: ignore[reportArgumentType]
    SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)
    HTTPXClientInstrumentor().instrument()


def shutdown_observability() -> None:
    """Flush the PostHog client on shutdown (best-effort, bounded). Called from
    the FastAPI lifespan `finally`."""
    events.shutdown_posthog()


def _init_otel(settings: Settings) -> None:
    """Wire the TracerProvider + OTLP/HTTP span exporter + pool gauges.

    Traces export to the shared Grafana Vector at `{endpoint}/v1/traces`
    (HTTP/protobuf). `ParentBased(ALWAYS_ON)` keeps the trace whole — a child
    span inherits the parent's sampling decision, and root spans are always
    sampled (low volume at launch; revisit when traffic grows). The Resource
    identifies this process in Tempo: service name/version, environment, and a
    per-Machine instance id.
    """
    from opentelemetry import trace  # type: ignore[import-not-found]
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
        BatchSpanProcessor,
    )
    from opentelemetry.sdk.trace.sampling import (  # type: ignore[import-not-found]
        ALWAYS_ON,
        ParentBased,
    )

    instance_id = settings.fly_machine_id or socket.gethostname()
    resource = Resource.create(
        {
            "service.name": "saferskills-api",
            "service.version": settings.version,
            "deployment.environment": settings.env,
            "service.instance.id": instance_id,
        }
    )
    provider = TracerProvider(resource=resource, sampler=ParentBased(ALWAYS_ON))
    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/")  # type: ignore[union-attr]
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    _init_db_pool_gauges(settings, resource)


def _init_db_pool_gauges(settings: Settings, resource: object) -> None:
    """Register OTel observable gauges on the shared SQLAlchemy pool.

    `ingestion.db_pool.in_use` / `.available` are the single most useful signal
    for "are we about to exhaust the pool the API and the ingestion worker share"
    — a Grafana alert at `in_use > 12 / 15` fires
    *before* contention turns into hangs.

    This wires the SDK MeterProvider + instruments but NO metric reader/exporter
    yet — metrics export is deferred to a separate openlatch-platform Vector PR.
    The callbacks register now and start being collected the moment a
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
