"""Shared scan-pipeline constants.

Kept in their own tiny module so the public-feed, sitemap, and IndexNow code
paths can all import the same source of truth without a circular import on the
`app.routers.scans` router module.
"""

from __future__ import annotations

# The bulk auto-scan run sources excluded from the public feed, the sitemap, AND
# IndexNow. A public scan from one of these is real but not individually citable
# (it is the firehose the durable reconciliation drainer produces), so it must
# never inflate the indexable surface (SEO-T9 / R4 sitewide quality defense).
FEED_EXCLUDED_SOURCES: tuple[str, ...] = ("ingestion", "rescan_rules")
