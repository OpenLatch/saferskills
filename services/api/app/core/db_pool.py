"""Shared asyncpg pool — exists alongside the SQLAlchemy AsyncSession factory.

Why a second connection path: SQLAlchemy's AsyncSession does NOT expose
PostgreSQL `LISTEN` / `NOTIFY`. The scan progress SSE stream and the in-process
queue worker need native pub-sub. asyncpg has it, so we keep a small dedicated
pool just for those two paths.

Every other read/write goes through `AsyncSessionLocal` per the project
standard. The pool is initialized in `main.py`'s lifespan and shut down on
process exit.
"""

from __future__ import annotations

import asyncpg

from app.core.config import coerce_ssl_to_sslmode, get_settings

_pool: asyncpg.Pool | None = None


def _sqlalchemy_dsn_to_asyncpg(url: str) -> str:
    """Render `settings.database_url` as a DSN raw `asyncpg.create_pool` accepts.

    Two transforms (mirrors `app.ingestion._libpq_conninfo`, which does the same
    for the Procrastinate psycopg connector): (1) strip the SQLAlchemy `+asyncpg`
    driver hint, and (2) rename the asyncpg-DIALECT `?ssl=…` query param back to
    libpq's `?sslmode=…`.

    Skipping (2) is silently fatal. `config.py::_normalize_db_dsn` renames the
    env DSN's libpq `?sslmode=…` → `?ssl=…` for the SQLAlchemy asyncpg *dialect*
    (which interprets `ssl=disable/require/…`). But RAW asyncpg's DSN parser does
    NOT: it reads `?ssl=disable` as a truthy string → enables TLS with a default
    SSLContext — the EXACT OPPOSITE of the intended "no SSL" — while it reads
    libpq `?sslmode=disable` → ssl=False correctly. So on a `sslmode=disable`
    Fly-internal/6PN DSN (no TLS), the un-renamed form makes `create_pool` attempt
    a TLS handshake against a non-TLS server and raise. `init_pool()` then leaves
    `_pool` None (the boot failure is non-fatal), and every SSE-emitting scan dies
    in `_emit`'s `get_pool()` — the prod "scan results not available" regression.
    """
    return coerce_ssl_to_sslmode(url.replace("postgresql+asyncpg://", "postgresql://", 1))


async def init_pool() -> asyncpg.Pool:
    """Open the shared asyncpg pool. Called from `lifespan` startup."""
    global _pool
    if _pool is not None:
        return _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(  # pyright: ignore[reportUnknownMemberType]
        _sqlalchemy_dsn_to_asyncpg(settings.database_url),
        min_size=1,
        max_size=settings.asyncpg_pool_max_size,  # budgeted
        command_timeout=10,
    )
    return _pool


async def close_pool() -> None:
    """Close the shared asyncpg pool. Called from `lifespan` shutdown."""
    global _pool
    if _pool is None:
        return
    await _pool.close()
    _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the live pool. Raises if `init_pool` has not run."""
    if _pool is None:
        raise RuntimeError(
            "asyncpg pool not initialized — ensure lifespan startup ran init_pool()."
        )
    return _pool
