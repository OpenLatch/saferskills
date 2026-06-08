"""Structured logging configuration via structlog.

All application code logs through structlog; third-party library records
(uvicorn / SQLAlchemy / …) are routed through the same JSON pipeline via the
stdlib logging bridge so every line is one machine-readable JSON object on
stdout — the format the shared Grafana Vector → Loki drain expects.

The load-bearing processor is `inject_trace_context`: it pulls the active OTel
span's `trace_id` / `span_id` onto every log line so Grafana can cross-navigate
Loki ↔ Tempo ("View trace" on a log line). It runs LAST in the chain — after any
redaction — because trace IDs are hex strings, never sensitive.

The existing capability-token redaction (`app.core.log_redaction`) is a separate
stdlib `logging.Filter` installed alongside this config (see
`app.core.observability.init_observability`); it is unaffected by this module.

Usage:
    from app.core.logging import configure_logging
    configure_logging(log_level="INFO")
"""

import logging
import sys

import structlog
from structlog.types import EventDict, WrappedLogger


def inject_trace_context(
    logger: WrappedLogger,  # structlog Processor signature
    method_name: str,  # structlog Processor signature
    event_dict: EventDict,
) -> EventDict:
    """Add `trace_id` / `span_id` from the active OTel span to the event dict.

    Enables Grafana Cloud Loki→Tempo cross-navigation: every log line emitted
    while a span is active gets a "View trace" button that resolves the matching
    Tempo span. See `.claude/rules/telemetry.md` § OpenTelemetry.

    No-op when:
      - `opentelemetry-api` is absent (the lazy import fails) — keeps this module
        importable in minimal test contexts.
      - No TracerProvider is configured (dev / no OTLP endpoint) — `get_current_
        span()` returns an INVALID_SPAN whose context `is_valid` is False.
      - No span is active on this execution context.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        return event_dict

    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return event_dict

    event_dict["trace_id"] = format(ctx.trace_id, "032x")
    event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with single-path JSON output to stdout.

    structlog routes through the stdlib `LoggerFactory` so ALL records
    (structlog-native AND foreign) pass through exactly one `ProcessorFormatter`
    → `JSONRenderer`. `foreign_pre_chain` enriches uvicorn/SQLAlchemy records
    before the shared processors run, so a uvicorn access line and an app event
    serialize identically — both carrying `trace_id` / `span_id` when a span is
    active.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared processors — `inject_trace_context` runs LAST so every line
    # (including foreign records) carries the active span's trace/span ids.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
        inject_trace_context,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            # Hand off to ProcessorFormatter for the final JSON render. Must be
            # last and must NOT itself be JSONRenderer here.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.ExceptionRenderer(),
                inject_trace_context,
            ],
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Let uvicorn loggers propagate to root so they flow through the JSON bridge
    # instead of installing their own plain-text handlers.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvi_logger = logging.getLogger(name)
        uvi_logger.handlers.clear()
        uvi_logger.propagate = True

    # Drop health-probe access lines at INFO+ — pure noise. Passed through only
    # when the root logger is at DEBUG.
    class _HealthCheckFilter(logging.Filter):
        _HEALTH_PATHS = ("/health", "/ready", "/api/v1/health", "/api/v1/ready")

        def filter(self, record: logging.LogRecord) -> bool:
            if logging.getLogger().level <= logging.DEBUG:
                return True
            msg = record.getMessage()
            return not any(path in msg for path in self._HEALTH_PATHS)

    logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())
