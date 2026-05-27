"""Database session + engine setup.

Single async engine bound to `settings.database_url`; an `AsyncSession` factory
that yields per-request sessions in routers.
"""

from app.db.session import AsyncSessionLocal, async_engine, get_session

__all__ = ["AsyncSessionLocal", "async_engine", "get_session"]
