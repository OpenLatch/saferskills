"""IP-bucket rate limiter backed by the existing `rate_limits` table.

W1 ships the `rate_limits` table with composite PK `(ip_hash, bucket, window_start)`
and a `count` column. Phase B is the first consumer.

The check is a single UPSERT: increment `count` for the current 24h window if it
exists, else insert a new row with `count=1`. If `count > limit` after the upsert,
raise HTTPException(429).

The IP is hashed (sha256) before storage so the raw value never lands at rest —
per `.claude/rules/security.md` § Operational retention.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

Bucket = Literal["scan_submit", "scan_read", "item_read", "item_list"]


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _window_start(now: datetime, window: timedelta) -> datetime:
    """Truncate `now` to the start of the current `window`-sized bucket.

    For window=1d this is the UTC midnight floor of `now`.
    """
    if window == timedelta(days=1):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Generic fallback: epoch-aligned bucket starts.
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    seconds_into = int((now - epoch).total_seconds()) % int(window.total_seconds())
    return now - timedelta(seconds=seconds_into, microseconds=now.microsecond)


async def enforce_ip_rate_limit(
    session: AsyncSession,
    ip: str,
    bucket: Bucket,
    limit: int,
    window: timedelta = timedelta(days=1),
) -> None:
    """Atomically check + increment the IP+bucket counter. Raise 429 if over.

    Uses INSERT ... ON CONFLICT to keep the read+write atomic. The returned
    count is the new value AFTER increment.
    """
    ip_hash = _hash_ip(ip)
    window_start = _window_start(datetime.now(UTC), window)

    stmt = text(
        """
        INSERT INTO rate_limits (ip_hash, bucket, window_start, count)
        VALUES (:ip_hash, :bucket, :window_start, 1)
        ON CONFLICT (ip_hash, bucket, window_start)
        DO UPDATE SET count = rate_limits.count + 1, updated_at = now()
        RETURNING count
        """
    )
    result = await session.execute(
        stmt,
        {"ip_hash": ip_hash, "bucket": bucket, "window_start": window_start},
    )
    await session.commit()
    new_count = result.scalar_one()

    if new_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: {limit} {bucket} requests per "
                f"{window.total_seconds():.0f}s. Try again later."
            ),
            headers={
                "Retry-After": str(int(window.total_seconds())),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )
