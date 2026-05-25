"""Alembic env.py — W1 minimal. No migrations yet.

The Track B rewrite (Initiative I-02) will populate this with the standard
async SQLAlchemy + Alembic pattern (offline + online targets, `Base.metadata`
import from app.models, etc.). At W1 we keep the file shape so `alembic
upgrade head` is a no-op rather than an import error.
"""

from logging.config import fileConfig

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # W1 stub: no real engine binding yet. Real impl lands W2.
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
