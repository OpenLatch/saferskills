"""Access-log redaction for capability tokens.

uvicorn logs the raw request path by default, which would write the unlisted
capability token (`/scans/r/<token>`) into access logs. This filter rewrites the
token segment to `<redacted>` before the log line is emitted — installed on the
uvicorn access logger + the root logger so neither uvicorn nor app logging leaks
the token.
"""

from __future__ import annotations

import logging

from app.observability.events import redact_capability_token

_TARGET_LOGGERS = ("uvicorn.access", "uvicorn", "")


class CapabilityTokenLogFilter(logging.Filter):
    """Redact `/scans/r/<token>` from a log record's message + args in place."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_capability_token(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_capability_token(a) if isinstance(a, str) else a for a in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                k: (redact_capability_token(v) if isinstance(v, str) else v)
                for k, v in record.args.items()
            }
        return True


def install_log_redaction() -> None:
    """Attach the token-redaction filter to the access + root loggers AND their
    handlers (idempotent). A logger-level filter only sees records emitted at that
    logger; a handler-level filter also sees records propagated from children, so
    both are attached to be robust to uvicorn's logging config."""
    flt = CapabilityTokenLogFilter()

    def _attach(target: logging.Logger | logging.Handler) -> None:
        if not any(isinstance(f, CapabilityTokenLogFilter) for f in target.filters):
            target.addFilter(flt)

    for name in _TARGET_LOGGERS:
        logger = logging.getLogger(name)
        _attach(logger)
        for handler in logger.handlers:
            _attach(handler)
