"""Fetch a GitHub repository tarball + resolve the ref SHA.

Network surface:

- `api.github.com/repos/<org>/<repo>` — resolve default branch + ref SHA.
- `codeload.github.com/<org>/<repo>/tar.gz/refs/heads/<branch>` — tarball.

Both hosts are GitHub-owned; no SSRF guard is needed beyond the allowlist of
those two hostnames (per `.claude/rules/security.md` § Public-input handling).

Limits:
- 25 MiB total tarball size — streamed; we abort on overflow.
- 5 MiB per file post-extract — files larger are skipped (logged as scan
  warnings, not as findings).
- 60 s overall timeout for the fetch + extract step.

Returns a `FetchResult(directory, ref_sha, file_count)` so the walker can
proceed against the extracted tree.
"""

from __future__ import annotations

import io
import re
import tarfile
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import get_settings

GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<org>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})?)/"
    r"(?P<repo>[A-Za-z0-9._-]+?)(?:/.*)?/?$"
)

MAX_TARBALL_BYTES = 25 * 1024 * 1024
MAX_PER_FILE_BYTES = 5 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 60.0


class FetchError(RuntimeError):
    """Tarball fetch failed or returned an invalid response."""


@dataclass(frozen=True)
class GithubRef:
    org: str
    repo: str


@dataclass
class FetchResult:
    directory: Path
    ref_sha: str
    file_count: int
    skipped_oversized_files: list[str]


def parse_github_url(github_url: str) -> GithubRef:
    """Validate + extract `<org>/<repo>` from a public GitHub URL."""
    match = GITHUB_URL_RE.match(github_url.strip().rstrip("/"))
    if match is None:
        raise FetchError(f"not a public github URL: {github_url!r}")
    return GithubRef(org=match.group("org"), repo=match.group("repo"))


def _auth_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SaferSkills-Scan-Engine/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _resolve_ref_sha(client: httpx.AsyncClient, ref: GithubRef) -> tuple[str, str]:
    """Return `(default_branch, head_sha)` for the repo at HEAD of default branch."""
    repo_response = await client.get(
        f"https://api.github.com/repos/{ref.org}/{ref.repo}",
        headers=_auth_headers(),
    )
    if repo_response.status_code == 404:
        raise FetchError(f"repo not found: {ref.org}/{ref.repo}")
    repo_response.raise_for_status()
    repo_body = repo_response.json()
    default_branch = repo_body.get("default_branch", "main")

    branch_response = await client.get(
        f"https://api.github.com/repos/{ref.org}/{ref.repo}/branches/{default_branch}",
        headers=_auth_headers(),
    )
    branch_response.raise_for_status()
    branch_body = branch_response.json()
    sha = branch_body.get("commit", {}).get("sha")
    if not isinstance(sha, str) or len(sha) != 40:
        raise FetchError(f"invalid HEAD sha for {ref.org}/{ref.repo}@{default_branch}")
    return default_branch, sha


async def _download_tarball(client: httpx.AsyncClient, ref: GithubRef, branch: str) -> bytes:
    """Stream the tarball with a hard size cap."""
    url = f"https://codeload.github.com/{ref.org}/{ref.repo}/tar.gz/refs/heads/{branch}"
    async with client.stream("GET", url, headers=_auth_headers()) as response:
        response.raise_for_status()
        buf = bytearray()
        async for chunk in response.aiter_bytes():
            buf.extend(chunk)
            if len(buf) > MAX_TARBALL_BYTES:
                raise FetchError(
                    f"tarball exceeded {MAX_TARBALL_BYTES} bytes; aborting (anti-DOS cap)"
                )
        return bytes(buf)


def _extract_tarball(blob: bytes, destination: Path) -> tuple[int, list[str]]:
    """Extract the tarball; skip oversized files. Returns (kept, skipped_paths)."""
    kept = 0
    skipped: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            if member.size > MAX_PER_FILE_BYTES:
                skipped.append(member.name)
                continue
            # Tarball entries are `<org>-<repo>-<sha>/path/to/file` — strip
            # the top-level prefix so paths the rubric's glob scope expects
            # actually match (e.g. `tools/manifest.json`, not
            # `acme-foo-abc1234/tools/manifest.json`).
            parts = Path(member.name).parts
            if len(parts) <= 1:
                continue
            inner_path = Path(*parts[1:])
            extracted_member = member
            extracted_member.name = str(inner_path)
            archive.extract(extracted_member, destination, filter="data")
            kept += 1
    return kept, skipped


async def fetch_repository(github_url: str) -> FetchResult:
    """Resolve + download + extract a GitHub repo into a temp dir.

    Caller owns the returned directory and is responsible for cleanup.
    """
    ref = parse_github_url(github_url)
    timeout = httpx.Timeout(FETCH_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        branch, sha = await _resolve_ref_sha(client, ref)
        tarball = await _download_tarball(client, ref, branch)

    workdir = Path(tempfile.mkdtemp(prefix="saferskills-scan-"))
    file_count, skipped = _extract_tarball(tarball, workdir)
    return FetchResult(
        directory=workdir,
        ref_sha=sha,
        file_count=file_count,
        skipped_oversized_files=skipped,
    )


def walk_files(directory: Path) -> Iterator[tuple[str, bytes]]:
    """Yield `(relative_path, content_bytes)` for every file in `directory`."""
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        try:
            yield (path.relative_to(directory).as_posix(), path.read_bytes())
        except OSError:
            continue
