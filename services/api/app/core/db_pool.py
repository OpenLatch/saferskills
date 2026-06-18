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

from app.core.config import get_settings

_pool: asyncpg.Pool | None = None


def _sqlalchemy_dsn_to_asyncpg(url: str) -> str:
    """Strip the SQLAlchemy `+asyncpg` driver hint so asyncpg.connect accepts it."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


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
