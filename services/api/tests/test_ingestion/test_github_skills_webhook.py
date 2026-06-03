"""Tests for GithubSkillsWebhookAdapter.verify_signature."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from app.ingestion.sources.github_skills_webhook import GithubSkillsWebhookAdapter


def _make_sig(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TestVerifySignature:
    def test_valid_signature_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = "test-webhook-secret-1234"
        body = b'{"event":"push","ref":"refs/heads/main"}'
        sig = _make_sig(secret, body)

        # Override settings.github_webhook_secret
        from app.core import config as config_module

        monkeypatch.setattr(config_module.get_settings(), "github_webhook_secret", secret)
        assert GithubSkillsWebhookAdapter.verify_signature(body, sig) is True  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

    def test_wrong_secret_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = b'{"event":"push"}'
        sig = _make_sig("real-secret", body)

        from app.core import config as config_module

        monkeypatch.setattr(config_module.get_settings(), "github_webhook_secret", "wrong-secret")
        assert GithubSkillsWebhookAdapter.verify_signature(body, sig) is False  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

    def test_missing_header_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core import config as config_module

        monkeypatch.setattr(config_module.get_settings(), "github_webhook_secret", "any-secret")
        assert GithubSkillsWebhookAdapter.verify_signature(b"body", None) is False  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

    def test_empty_header_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core import config as config_module

        monkeypatch.setattr(config_module.get_settings(), "github_webhook_secret", "any-secret")
        assert GithubSkillsWebhookAdapter.verify_signature(b"body", "") is False  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

    def test_header_without_sha256_prefix_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "my-secret"
        body = b"data"
        raw_digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        # Header without the "sha256=" prefix
        from app.core import config as config_module

        monkeypatch.setattr(config_module.get_settings(), "github_webhook_secret", secret)
        assert GithubSkillsWebhookAdapter.verify_signature(body, raw_digest) is False  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

    def test_no_webhook_secret_configured_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core import config as config_module

        monkeypatch.setattr(config_module.get_settings(), "github_webhook_secret", None)
        sig = _make_sig("whatever", b"payload")
        assert GithubSkillsWebhookAdapter.verify_signature(b"payload", sig) is False  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

    def test_tampered_body_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        secret = "secret"
        original_body = b"original payload"
        sig = _make_sig(secret, original_body)

        from app.core import config as config_module

        monkeypatch.setattr(config_module.get_settings(), "github_webhook_secret", secret)
        # Same sig but different body
        assert GithubSkillsWebhookAdapter.verify_signature(b"tampered payload", sig) is False  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
