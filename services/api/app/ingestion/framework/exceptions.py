"""Ingestion error taxonomy."""

from __future__ import annotations


class IngestionError(Exception):
    """Base class for all ingestion-framework errors."""


class AdapterBlockedError(IngestionError):
    """The source actively blocked us (Cloudflare challenge, hard 403). Halts only this adapter."""


class AdapterPausedError(IngestionError):
    """The source is operator-paused (founder halt switch). The cycle is a no-op."""


class RobotsTxtDisallow(IngestionError):
    """robots.txt disallows the path we were about to fetch (aggregator scraping)."""


class OutboundDenyError(IngestionError):
    """An outbound request targeted a host outside the adapter's SOURCE_HOSTS allowlist."""


class BodyTooLargeError(IngestionError):
    """A response body exceeded the 25 MiB per-fetch cap (security.md)."""
