"""Alembic env.py — async SQLAlchemy + `Base.metadata` autogenerate target.

W2 Phase A rewrite. The hand-written `0001_initial_scan_surface.py` migration
is the source-of-truth for the DB schema; `target_metadata = Base.metadata`
enables autogenerate to compare future model edits against the DB once the
Phase B SQLAlchemy generator emits real (non-stub) models.
"""

from __future__ import annotations

import asyncio
import contextlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings

# Import Base so that target_metadata is non-empty after the model package's
# __init__ imports its generated members. Side-effect imports keep autogenerate
# aware of every table without a hand-maintained registry.
from app.models.base import Base

# Best-effort import of the generated models package so its side-effects
# register tables on Base.metadata. The package may be empty on a fresh
# checkout before `pnpm run generate` runs — that's fine, hand-written
# migrations still work.
with contextlib.suppress(ImportError):
    import app.models.generated  # noqa: F401

config = context.config

# Resolve sqlalchemy.url from app settings rather than from alembic.ini so the
# same DATABASE_URL drives both runtime and migrations. alembic.ini still
# carries a fallback for `alembic upgrade` invocations that don't load app
# settings (rare).
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL to stdout."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
