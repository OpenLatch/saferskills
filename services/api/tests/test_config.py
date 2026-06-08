"""Regression tests for `app.core.config.Settings`.

Covers the DSN normalization that keeps the API from crashing on boot when
`DATABASE_URL` arrives in a managed-Postgres shape. The `_normalize_db_dsn`
validator handles two such quirks:
  - scheme: a `postgres://` DSN (Fly's `postgres attach` default) once made
    `create_async_engine` raise `NoSuchModuleError: sqlalchemy.dialects:postgres`
    and the staging machines crash-looped to their max restart count;
  - SSL: a `?sslmode=require` query param (Fly Managed Postgres / Supabase /
    Neon) made the asyncpg dialect raise `connect() got an unexpected keyword
    argument 'sslmode'` at `alembic upgrade head`, dropping the API into
    degraded mode (503 on every route but `/api/v1/health`) and failing the
    staging e2e doctor probe.
"""

from typing import Literal

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings

EnvTier = Literal["development", "staging", "production"]


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The staging breakage: a managed-Postgres `?sslmode=require` rejected by
        # the asyncpg dialect as a bad connect() kwarg → renamed to `ssl`.
        (
            "postgresql+asyncpg://u:p@host:5432/db?sslmode=require",
            "postgresql+asyncpg://u:p@host:5432/db?ssl=require",
        ),
        # All libpq sslmode values map straight across to asyncpg's `ssl`.
        (
            "postgresql+asyncpg://u:p@host:5432/db?sslmode=disable",
            "postgresql+asyncpg://u:p@host:5432/db?ssl=disable",
        ),
        # Scheme + sslmode quirks are fixed together in one pass.
        (
            "postgres://u:p@host:5432/db?sslmode=verify-full",
            "postgresql+asyncpg://u:p@host:5432/db?ssl=verify-full",
        ),
        # Other query params are preserved; only sslmode is renamed.
        (
            "postgresql+asyncpg://u:p@host:5432/db?sslmode=require&application_name=ss",
            "postgresql+asyncpg://u:p@host:5432/db?ssl=require&application_name=ss",
        ),
        # An explicit `ssl` wins — the libpq alias is dropped, not duplicated.
        (
            "postgresql+asyncpg://u:p@host:5432/db?ssl=require&sslmode=require",
            "postgresql+asyncpg://u:p@host:5432/db?ssl=require",
        ),
        # No SSL param → DSN is untouched.
        (
            "postgresql+asyncpg://u:p@host:5432/db",
            "postgresql+asyncpg://u:p@host:5432/db",
        ),
    ],
)
def test_database_url_sslmode_is_coerced_to_ssl(raw: str, expected: str) -> None:
    assert Settings(database_url=raw).database_url == expected


def test_sslmode_dsn_builds_an_async_engine_without_raising() -> None:
    """A `?sslmode=…` DSN must yield an engine the asyncpg dialect can dispatch.

    Regression for the staging boot failure: before the coercion,
    `create_async_engine(...).connect()` raised `connect() got an unexpected
    keyword argument 'sslmode'`. The dialect must now accept the normalized DSN
    (we assert the dialect resolves; an actual connect is covered by e2e).
    """
    settings = Settings(database_url="postgresql+asyncpg://u:p@host:5432/db?sslmode=require")
    engine = create_async_engine(settings.database_url)
    assert engine.dialect.driver == "asyncpg"
    assert "sslmode" not in str(engine.url)
    assert engine.url.query.get("ssl") == "require"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The Procrastinate breakage: the asyncpg `?ssl=disable` (what
        # `_normalize_db_dsn` produces) rejected by libpq → renamed to `sslmode`.
        (
            "postgresql://u:p@host:5432/db?ssl=disable",
            "postgresql://u:p@host:5432/db?sslmode=disable",
        ),
        # All values map straight across.
        (
            "postgresql://u:p@host:5432/db?ssl=require",
            "postgresql://u:p@host:5432/db?sslmode=require",
        ),
        # `sslmode=` is NOT touched (it is not a substring match of `ssl=`).
        (
            "postgresql://u:p@host:5432/db?sslmode=require",
            "postgresql://u:p@host:5432/db?sslmode=require",
        ),
        # Other params preserved; only `ssl` is renamed.
        (
            "postgresql://u:p@host:5432/db?ssl=disable&application_name=ss",
            "postgresql://u:p@host:5432/db?sslmode=disable&application_name=ss",
        ),
        # An explicit `sslmode` wins — the asyncpg alias is dropped, not duplicated.
        (
            "postgresql://u:p@host:5432/db?sslmode=require&ssl=require",
            "postgresql://u:p@host:5432/db?sslmode=require",
        ),
        # No SSL param at all → untouched.
        ("postgresql://u:p@host:5432/db", "postgresql://u:p@host:5432/db"),
    ],
)
def test_ssl_query_param_is_coerced_back_to_sslmode(raw: str, expected: str) -> None:
    from app.core.config import _coerce_ssl_to_sslmode

    assert _coerce_ssl_to_sslmode(raw) == expected


def test_libpq_conninfo_renames_ssl_for_psycopg() -> None:
    """Regression: the Procrastinate psycopg pool DSN must use libpq `sslmode`.

    `settings.database_url` carries the asyncpg `?ssl=disable` form, but libpq
    rejects `ssl` (`invalid URI query parameter: "ssl"`), so every psycopg pool
    connection failed and `open_async()` died with `PoolTimeout: pool
    initialization incomplete after 30.0 sec` — degrading the ingestion worker on
    every boot. `_libpq_conninfo` must strip the driver suffix AND rename `ssl`.
    """
    from app.ingestion import _libpq_conninfo

    out = _libpq_conninfo("postgresql+asyncpg://u:p@host:5432/db?ssl=disable")
    assert out == "postgresql://u:p@host:5432/db?sslmode=disable"
    assert "ssl=disable" not in out  # the libpq-fatal token is gone


# ── Turnstile secret startup guard ──────────────────────────────────────────


def test_turnstile_secret_optional_in_dev() -> None:
    """Dev/test tolerate a missing Turnstile secret — the gate bypasses there."""
    settings = Settings(env="development", turnstile_secret_key=None)
    assert settings.turnstile_secret_key is None


@pytest.mark.parametrize("env", ["staging", "production"])
def test_turnstile_secret_required_in_prod(env: EnvTier) -> None:
    """Boot MUST hard-fail when the gate would otherwise run open in prod/staging."""
    with pytest.raises(ValueError, match="TURNSTILE_SECRET_KEY"):
        Settings(env=env, turnstile_secret_key=None)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_turnstile_secret_present_passes_in_prod(env: EnvTier) -> None:
    # Both prod-required secrets must be present for boot to pass (Turnstile +
    # the CLI Proof-of-Work secret — see config.py model_validator).
    settings = Settings(
        env=env, turnstile_secret_key="1x000...AA", saferskills_cli_pow_secret="prod-pow-secret"
    )
    assert settings.turnstile_secret_key == "1x000...AA"
    assert settings.saferskills_cli_pow_secret == "prod-pow-secret"


def test_cli_pow_secret_optional_in_dev() -> None:
    """Dev/test tolerate a missing CLI PoW secret — /cli-challenge 503s there."""
    settings = Settings(env="development", saferskills_cli_pow_secret=None)
    assert settings.saferskills_cli_pow_secret is None


@pytest.mark.parametrize("env", ["staging", "production"])
def test_cli_pow_secret_required_in_prod(env: EnvTier) -> None:
    """Boot MUST hard-fail when the stateless PoW gate has no trust anchor in prod."""
    with pytest.raises(ValueError, match="SAFERSKILLS_CLI_POW_SECRET"):
        Settings(env=env, turnstile_secret_key="1x000...AA", saferskills_cli_pow_secret=None)
