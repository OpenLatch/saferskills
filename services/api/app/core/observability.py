"""Observability bootstrap — Sentry + OpenTelemetry.

W1 posture: every initialiser is a no-op when its env var is unset, so
`docker compose up` works against a fresh checkout without secrets.
"""

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)


async def init_observability(settings: Settings) -> None:
    if settings.sentry_dsn:
        try:
            import sentry_sdk  # type: ignore[import-not-found]
            from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore[import-not-found]

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                integrations=[FastApiIntegration()],
                release=f"saferskills-api@{settings.version}+{settings.git_sha[:7]}",
                send_default_pii=False,
                traces_sample_rate=0.0,  # bumped per-environment from Fly secrets later
            )
            logger.info("sentry.initialised")
        except Exception as exc:  # noqa: BLE001 — observability must never break the app
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
            logger.info("otel.initialised")
        except Exception as exc:  # noqa: BLE001 — observability must never break the app
            logger.warning("otel.init_failed", error=str(exc))
