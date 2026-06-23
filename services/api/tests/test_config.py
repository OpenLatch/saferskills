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

import base64
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
    from app.core.config import coerce_ssl_to_sslmode

    assert coerce_ssl_to_sslmode(raw) == expected


def test_libpq_conninfo_renames_ssl_for_psycopg() -> None:
    """Regression: the Procrastinate psycopg pool DSN must use libpq `sslmode`.

    `settings.database_url` carries the asyncpg `?ssl=disable` form, but libpq
    rejects `ssl` (`invalid URI query parameter: "ssl"`), so every psycopg pool
    connection failed and `open_async()` died with `PoolTimeout: pool
    initialization incomplete after 30.0 sec` — degrading the ingestion worker on
    every boot. `_libpq_conninfo` must strip the driver suffix AND rename `ssl`.
    """
    from app.ingestion import _libpq_conninfo  # pyright: ignore[reportPrivateUsage]

    out = _libpq_conninfo("postgresql+asyncpg://u:p@host:5432/db?ssl=disable")
    assert out == "postgresql://u:p@host:5432/db?sslmode=disable"
    assert "ssl=disable" not in out  # the libpq-fatal token is gone


def test_db_pool_dsn_renames_ssl_to_sslmode_for_raw_asyncpg() -> None:
    """Regression: the asyncpg LISTEN/NOTIFY pool DSN must use libpq `sslmode`.

    `settings.database_url` carries the asyncpg-dialect `?ssl=disable` form, but
    RAW `asyncpg.create_pool` misreads `ssl=disable` as a truthy string → ENABLES
    TLS (default SSLContext), the opposite of intent — so on a `sslmode=disable`
    Fly-internal DSN it attempts a TLS handshake against a non-TLS server and
    `create_pool` raises. `init_pool()` then leaves the pool None and every
    SSE-emitting scan dies in `_emit`'s `get_pool()` (the prod "scan results not
    available" regression). `_sqlalchemy_dsn_to_asyncpg` must strip the driver
    suffix AND rename `ssl` → `sslmode` so asyncpg parses it correctly.
    """
    from app.core.db_pool import (
        _sqlalchemy_dsn_to_asyncpg,  # pyright: ignore[reportPrivateUsage]
    )

    out = _sqlalchemy_dsn_to_asyncpg("postgresql+asyncpg://u:p@host:5432/db?ssl=disable")
    assert out == "postgresql://u:p@host:5432/db?sslmode=disable"
    assert "ssl=disable" not in out  # asyncpg would misread this as "enable TLS"
    # A plain (no-SSL) DSN still loses only the driver hint, untouched otherwise.
    assert (
        _sqlalchemy_dsn_to_asyncpg("postgresql+asyncpg://u:p@host:5432/db")
        == "postgresql://u:p@host:5432/db"
    )


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
    # ALL prod-required secrets must be present for boot to pass (Turnstile + the
    # CLI Proof-of-Work secret + the two agent-scan crypto anchors — see config.py
    # model_validator).
    settings = Settings(
        env=env,
        turnstile_secret_key="1x000...AA",
        saferskills_cli_pow_secret="prod-pow-secret",
        saferskills_agent_master_key="prod-agent-master-key",
        saferskills_pack_signing_key="prod-pack-signing-key",
        vendor_session_secret="prod-vendor-session-secret-0123456789",
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


def test_agent_master_key_required_in_prod() -> None:
    """Boot MUST hard-fail when the canary/run-token master key is unset in prod."""
    with pytest.raises(ValueError, match="SAFERSKILLS_AGENT_MASTER_KEY"):
        Settings(
            env="production",
            turnstile_secret_key="1x000...AA",
            saferskills_cli_pow_secret="prod-pow-secret",
            saferskills_agent_master_key=None,
            saferskills_pack_signing_key="k",
        )


def test_pack_signing_key_required_in_prod() -> None:
    """Boot MUST hard-fail when the Ed25519 pack-signing key is unset in prod."""
    with pytest.raises(ValueError, match="SAFERSKILLS_PACK_SIGNING_KEY"):
        Settings(
            env="production",
            turnstile_secret_key="1x000...AA",
            saferskills_cli_pow_secret="prod-pow-secret",
            saferskills_agent_master_key="k",
            saferskills_pack_signing_key=None,
        )


def test_agent_scan_secrets_optional_in_dev() -> None:
    """Dev/test tolerate missing agent-scan secrets — packs serve unsigned + a dev key."""
    settings = Settings(env="development")
    assert settings.saferskills_agent_master_key is None
    assert settings.saferskills_pack_signing_key is None


def test_vendor_session_secret_default_tolerated_in_dev() -> None:
    """Dev/test keep the placeholder vendor-session key — the guard is prod-only."""
    settings = Settings(env="development")
    assert settings.vendor_session_secret.startswith("dev-insecure")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_vendor_session_secret_default_rejected_in_prod(env: EnvTier) -> None:
    """Boot MUST hard-fail when the public dev vendor-session key reaches prod/staging.

    The default ships in the open-source repo, so leaving it set would mint forgeable
    verified-vendor right-of-reply sessions.
    """
    with pytest.raises(ValueError, match="VENDOR_SESSION_SECRET"):
        Settings(
            env=env,
            turnstile_secret_key="1x000...AA",
            saferskills_cli_pow_secret="prod-pow-secret",
            saferskills_agent_master_key="k",
            saferskills_pack_signing_key="k",
            # vendor_session_secret left at the insecure default
        )


@pytest.mark.parametrize("env", ["staging", "production"])
def test_vendor_session_secret_too_short_rejected_in_prod(env: EnvTier) -> None:
    """A non-default but weak (<32 byte) vendor-session key is also rejected in prod."""
    with pytest.raises(ValueError, match="VENDOR_SESSION_SECRET"):
        Settings(
            env=env,
            turnstile_secret_key="1x000...AA",
            saferskills_cli_pow_secret="prod-pow-secret",
            saferskills_agent_master_key="k",
            saferskills_pack_signing_key="k",
            vendor_session_secret="too-short",
        )


# ── GitHub App private key (base64-in-secret) normalization ──────────────────
#
# Regression: the key is stored base64-encoded in the `GITHUB_APP_PRIVATE_KEY_B64`
# Fly secret, but nothing decoded it — so `github_app_private_key` was always None,
# `get_github_app_installation_token` returned None, and every API + worker GitHub
# call ran ANONYMOUS (60 req/h). That throttled ingestion enrichment (empty-tier
# items hidden from the catalog) and 429'd the auto-scan pipeline.

_FAKE_PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIfake\n-----END RSA PRIVATE KEY-----\n"
_FAKE_PEM_B64 = base64.b64encode(_FAKE_PEM.encode()).decode()


def test_github_app_key_b64_secret_is_decoded_to_pem() -> None:
    """The deployed shape: a base64 `GITHUB_APP_PRIVATE_KEY_B64` secret → raw PEM."""
    settings = Settings(github_app_private_key_b64=_FAKE_PEM_B64)
    assert settings.github_app_private_key == _FAKE_PEM


def test_github_app_key_raw_pem_is_kept_as_is() -> None:
    """A raw multi-line PEM in the main field is used verbatim (no decode)."""
    settings = Settings(github_app_private_key=_FAKE_PEM)
    assert settings.github_app_private_key == _FAKE_PEM


def test_github_app_key_base64_in_main_field_is_decoded() -> None:
    """A base64 value placed in the main field is decoded too (lenient)."""
    settings = Settings(github_app_private_key=_FAKE_PEM_B64)
    assert settings.github_app_private_key == _FAKE_PEM


def test_github_app_key_invalid_value_degrades_to_none() -> None:
    """A non-PEM, non-base64 value resets to None so token minting fails gracefully."""
    settings = Settings(github_app_private_key="not-a-key-and-not-base64-$$$")
    assert settings.github_app_private_key is None


def test_github_app_key_unset_stays_none() -> None:
    settings = Settings()
    assert settings.github_app_private_key is None
