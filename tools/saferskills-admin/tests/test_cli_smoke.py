"""Smoke + safety-gate tests for saferskills-admin (no network)."""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from saferskills_admin.cli import app
from saferskills_admin.shared.http_client import _prefer_ipv4_localhost
from saferskills_admin.shared.safety import DANGEROUS_OPS, require_confirmation

runner = CliRunner()


def test_localhost_rewritten_to_ipv4() -> None:
    # On Windows `localhost` resolves to IPv6 ::1 first and uvicorn binds IPv4
    # only, stalling ~2s/request. The host-exact rewrite avoids that.
    assert _prefer_ipv4_localhost("http://localhost:8000") == "http://127.0.0.1:8000"
    assert _prefer_ipv4_localhost("http://localhost") == "http://127.0.0.1"
    assert _prefer_ipv4_localhost("https://localhost:9/x") == "https://127.0.0.1:9/x"


def test_non_localhost_urls_untouched() -> None:
    # Only a bare `localhost` host is rewritten — never a real remote.
    assert _prefer_ipv4_localhost("http://localhost.evil.com:8000") == (
        "http://localhost.evil.com:8000"
    )
    assert _prefer_ipv4_localhost("https://api.saferskills.ai") == "https://api.saferskills.ai"
    assert _prefer_ipv4_localhost("http://127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_help_lists_five_subapps() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in ("sources", "merge-candidates", "catalog", "popularity", "auth"):
        assert sub in result.output


def test_gen_admin_key_format() -> None:
    result = runner.invoke(app, ["auth", "gen-admin-key"])
    assert result.exit_code == 0
    key = result.output.strip()
    assert key.startswith("opk_admin_")
    assert len(key) == len("opk_admin_") + 64  # 32 bytes hex


def test_dangerous_op_blocked_without_yes() -> None:
    with pytest.raises(typer.Exit):
        require_confirmation("catalog archive", yes=False)


def test_dangerous_op_allowed_with_yes() -> None:
    # Should not raise.
    require_confirmation("catalog archive", yes=True)


def test_safe_op_never_gated() -> None:
    require_confirmation("sources list", yes=False)  # not in DANGEROUS_OPS → no raise
    assert "catalog archive" in DANGEROUS_OPS


def test_dangerous_op_allowed_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAFERSKILLS_ADMIN_CONFIRM", "yes-i-mean-it")
    require_confirmation("merge-candidates approve", yes=False)
