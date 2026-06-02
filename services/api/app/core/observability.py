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
            logger.info("otel.initialised")
        except Exception as exc:  # observability must never break the app
            logger.warning("otel.init_failed", error=str(exc))
