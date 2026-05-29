"""Regression tests for `app.core.config.Settings`.

Covers the DSN-scheme normalization that keeps the API from crashing on boot
when `DATABASE_URL` arrives in the managed-Postgres `postgres://` form (Fly's
`postgres attach` default). Before the `_normalize_db_scheme` validator,
`create_async_engine` raised `NoSuchModuleError: sqlalchemy.dialects:postgres`
and the staging machines crash-looped to their max restart count.
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Fly / Heroku-style managed DSN — the one that crashed staging.
        (
            "postgres://u:p@host:5432/db",
            "postgresql+asyncpg://u:p@host:5432/db",
        ),
        # Bare postgresql:// with no driver still needs the async driver.
        (
            "postgresql://u:p@host:5432/db",
            "postgresql+asyncpg://u:p@host:5432/db",
        ),
        # Already-correct async DSN is left untouched.
        (
            "postgresql+asyncpg://u:p@host:5432/db",
            "postgresql+asyncpg://u:p@host:5432/db",
        ),
        # An explicit non-asyncpg driver is respected, not clobbered.
        (
            "postgresql+psycopg://u:p@host:5432/db",
            "postgresql+psycopg://u:p@host:5432/db",
        ),
    ],
)
def test_database_url_scheme_is_normalized(raw: str, expected: str) -> None:
    assert Settings(database_url=raw).database_url == expected


def test_normalized_postgres_dsn_builds_an_async_engine() -> None:
    """The whole point: a `postgres://` DSN must yield a usable async engine."""
    settings = Settings(database_url="postgres://u:p@host:5432/db")
    engine = create_async_engine(settings.database_url)
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "asyncpg"
