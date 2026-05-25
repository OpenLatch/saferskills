"""Runtime configuration for the SaferSkills E2E suite.

Two sources, layered (later wins):
  1. Environment variables (`SAFERSKILLS_API_URL`, `SAFERSKILLS_BASE_URL`).
  2. CLI flags (`--api-url`, `--base-url`).

The repo root is discovered by walking up from this file until a
directory containing a `.git` folder is found; the screenshot directory
defaults to `<repo_root>/.local/screenshots/` so artefacts stay out of
version control.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def _repo_root() -> Path:
    """Find the repo root by walking up to the first `.git` directory.

    Falls back to the current working directory when invoked outside a
    git checkout (e.g. an installed wheel) so the screenshot dir is
    always writeable.
    """
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / ".git").exists():
            return parent
    return Path.cwd()


_DEFAULT_SCREENSHOT_DIR = _repo_root() / ".local" / "screenshots"


class Config(BaseModel):
    """Resolved configuration shared by every command.

    Pydantic validates that `api_url` / `base_url` parse as URLs and
    that the timeout is a positive float. `ensure_screenshot_dir` is
    called lazily by commands that need it, so `doctor` / `smoke` do
    not pay the mkdir cost.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_url: str = Field(
        default="http://localhost:8000",
        description="Root URL of the SaferSkills FastAPI backend.",
    )
    base_url: str = Field(
        default="http://localhost:5173",
        description="Root URL of the public marketing site.",
    )
    request_timeout_seconds: float = Field(default=10.0, gt=0.0)
    screenshot_dir: Path = Field(default=_DEFAULT_SCREENSHOT_DIR)

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Self:
        """Overlay CLI flags onto env-loaded defaults.

        CLI wins over env when both are present; env wins over the
        baked-in defaults. Stripping trailing slashes here means every
        downstream `f"{config.api_url}/api/v1/health"` is a clean join.
        """
        env_api = os.environ.get("SAFERSKILLS_API_URL")
        env_base = os.environ.get("SAFERSKILLS_BASE_URL")

        cli_api: str | None = getattr(args, "api_url", None)
        cli_base: str | None = getattr(args, "base_url", None)

        api_url = (cli_api or env_api or "http://localhost:8000").rstrip("/")
        base_url = (cli_base or env_base or "http://localhost:5173").rstrip("/")

        # Validate URL shape via pydantic's HttpUrl — we keep the string
        # form on the model because httpx + playwright want str, not
        # Url. A bad URL surfaces as pydantic.ValidationError caught by
        # the CLI dispatcher and mapped to ExitCode.FAIL_CONFIG.
        HttpUrl(api_url)
        HttpUrl(base_url)

        return cls(api_url=api_url, base_url=base_url)

    def ensure_screenshot_dir(self) -> Path:
        """Create the screenshot dir on demand and return its path."""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        return self.screenshot_dir
