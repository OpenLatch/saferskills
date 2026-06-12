"""Fetch a GitHub repository + resolve the ref SHA.

Network surface:

- `api.github.com/repos/<org>/<repo>` — resolve default branch + ref SHA + size.
- `codeload.github.com/<org>/<repo>/tar.gz/refs/heads/<branch>` — tarball (small repos).
- `api.github.com/repos/<org>/<repo>/git/trees/<sha>?recursive=1` — tree listing (large repos).
- `raw.githubusercontent.com/<org>/<repo>/<sha>/<path>` — per-blob fetch (large repos).

All hosts are GitHub-owned; no SSRF guard is needed beyond the allowlist of
those hostnames (per `.claude/rules/security.md` § Public-input handling #2).

Two fetch paths converge on the same `list[(path, bytes)]` file-index contract:

- **Small repos** → a single gzipped tarball (`fetch_repository` → `walk_files`),
  capped at 25 MiB streamed; a file > 5 MiB is skipped at extraction.
- **Large repos** (monorepos / `awesome-*` collections that blow the tarball cap)
  → list the tree via the Git Trees API (1 REST call, pinned to the resolved
  HEAD SHA) + download only the blobs ≤ 5 MiB via `raw.githubusercontent.com`
  (`fetch_file_index_via_trees`). Fetches exactly the set the tarball path keeps
  after its > 5 MiB skip, so scores + snapshot + zip stay byte-identical.

Limits:
- 25 MiB total tarball size — streamed; we abort on overflow (`TarballTooLargeError`).
  This caps the COMPRESSED stream only; the in-memory index bound below is what
  bounds the uncompressed bytes that actually sit in RAM.
- 5 MiB per file — files larger are skipped (logged as scan warnings, not findings).
- Per-repo in-memory index bounds (`scan_max_index_files` /
  `scan_max_index_total_bytes`) cap what EITHER fetch path admits to the
  `list[(path, bytes)]` index — applied in sorted-path order on both paths via
  `select_index_within_bounds`, so the kept fileset is identical regardless of
  fetch path. Over-bounds files are skipped gracefully (recorded on the report).
- 60 s overall timeout for the fetch + extract step.

Returns a `FetchResult(directory, ref_sha, file_count)` so the walker can
proceed against the extracted tree.
"""

from __future__ import annotations

import asyncio
import io
import re
import tarfile
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
import structlog

from app.core.config import get_settings
from app.core.github_app_token import get_github_app_installation_token

logger = structlog.get_logger(__name__)

GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<org>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})?)/"
    r"(?P<repo>[A-Za-z0-9._-]+?)(?:/.*)?/?$"
)

MAX_TARBALL_BYTES = 25 * 1024 * 1024
MAX_PER_FILE_BYTES = 5 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 60.0


class FetchError(RuntimeError):
    """Repo fetch failed or returned an invalid response."""


class TarballTooLargeError(FetchError):
    """The streamed tarball exceeded the 25 MiB anti-DOS cap.

    A `FetchError` subclass so existing `except FetchError` callers are
    unaffected, but distinguishable so the auto-scan pipeline can fall back to
    the Git Trees + raw path (a misclassified large repo) instead of treating
    it as a permanent failure.
    """


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


@dataclass
class ResolvedRef:
    """Result of a conditional HEAD-ref resolve (the scan-job change gate).

    `not_modified` is True when api.github.com returned 304 to our conditional
    request — the repo is unchanged since the stored validators, so the scan job
    skips the scan and just bumps `last_checked_at`. On a 200, `ref_sha` /
    `etag` / `last_modified` carry the fresh values to persist.
    """

    org: str
    repo: str
    default_branch: str | None
    ref_sha: str | None
    etag: str | None
    last_modified: str | None
    not_modified: bool
    size_kb: int | None = None
    """Repo size in KiB from the `repos/<org>/<repo>` payload (free — no extra
    request). Routes the auto-scan pipeline to the Git Trees + raw path for a
    large repo. `None` on the 304 path (which skips the scan anyway)."""


async def _auth_headers() -> dict[str, str]:
    """Build GitHub request headers, unifying scan fetch onto the ingestion identity.

    Prefer an explicit `GITHUB_TOKEN` PAT, else the shared GitHub App installation
    token (same 5,000 req/h budget as the ingestion adapters), else anonymous
    (60 req/h). See `app/core/github_app_token.py`.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SaferSkills-Scan-Engine/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    settings = get_settings()
    token = settings.github_token
    if not token:
        token = await get_github_app_installation_token(settings)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def resolve_ref(
    github_url: str, *, etag: str | None = None, last_modified: str | None = None
) -> ResolvedRef:
    """Conditionally resolve the repo's HEAD ref SHA (the scan-job change gate).

    Sends `If-None-Match` / `If-Modified-Since` against the repo endpoint (its
    ETag changes on every push, so a 304 means "no new commit" — a free hit
    against the GitHub budget). On 304 returns `not_modified=True`; on 200 it
    follows up with the branch endpoint to read the HEAD commit SHA + returns the
    fresh validators to persist in `repo_fetch_state`.
    """
    ref = parse_github_url(github_url)
    headers = await _auth_headers()
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    timeout = httpx.Timeout(FETCH_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        repo_response = await client.get(
            f"https://api.github.com/repos/{ref.org}/{ref.repo}", headers=headers
        )
        if repo_response.status_code == 304:
            return ResolvedRef(
                org=ref.org,
                repo=ref.repo,
                default_branch=None,
                ref_sha=None,
                etag=etag,
                last_modified=last_modified,
                not_modified=True,
            )
        if repo_response.status_code == 404:
            raise FetchError(f"repo not found: {ref.org}/{ref.repo}")
        repo_response.raise_for_status()
        new_etag = repo_response.headers.get("etag")
        new_last_modified = repo_response.headers.get("last-modified")
        repo_body = repo_response.json()
        default_branch = repo_body.get("default_branch", "main")
        raw_size = repo_body.get("size")
        size_kb = raw_size if isinstance(raw_size, int) else None

        branch_headers = await _auth_headers()
        branch_response = await client.get(
            f"https://api.github.com/repos/{ref.org}/{ref.repo}/branches/{default_branch}",
            headers=branch_headers,
        )
        if branch_response.status_code == 404:
            # Default branch unresolvable — repo deleted mid-window, an empty repo
            # with no commits, or a renamed branch. Permanent: a retry re-resolves
            # to the same 404. Raise FetchError (not the raw HTTPStatusError) so the
            # caller's `except FetchError` stamps recency + logs cleanly instead of
            # re-raising into 3 wasted Procrastinate retries + a traceback.
            raise FetchError(f"branch not found: {ref.org}/{ref.repo}@{default_branch}")
        branch_response.raise_for_status()
        sha = branch_response.json().get("commit", {}).get("sha")
        if not isinstance(sha, str) or len(sha) != 40:
            raise FetchError(f"invalid HEAD sha for {ref.org}/{ref.repo}@{default_branch}")
        return ResolvedRef(
            org=ref.org,
            repo=ref.repo,
            default_branch=default_branch,
            ref_sha=sha,
            etag=new_etag,
            last_modified=new_last_modified,
            not_modified=False,
            size_kb=size_kb,
        )


async def _resolve_ref_sha(client: httpx.AsyncClient, ref: GithubRef) -> tuple[str, str]:
    """Return `(default_branch, head_sha)` for the repo at HEAD of default branch."""
    repo_response = await client.get(
        f"https://api.github.com/repos/{ref.org}/{ref.repo}",
        headers=await _auth_headers(),
    )
    if repo_response.status_code == 404:
        raise FetchError(f"repo not found: {ref.org}/{ref.repo}")
    repo_response.raise_for_status()
    repo_body = repo_response.json()
    default_branch = repo_body.get("default_branch", "main")

    branch_response = await client.get(
        f"https://api.github.com/repos/{ref.org}/{ref.repo}/branches/{default_branch}",
        headers=await _auth_headers(),
    )
    if branch_response.status_code == 404:
        # Default branch unresolvable (deleted mid-window / empty repo / renamed) —
        # permanent, so surface as FetchError (not the raw HTTPStatusError) for the
        # caller's clean permanent-failure handling.
        raise FetchError(f"branch not found: {ref.org}/{ref.repo}@{default_branch}")
    branch_response.raise_for_status()
    branch_body = branch_response.json()
    sha = branch_body.get("commit", {}).get("sha")
    if not isinstance(sha, str) or len(sha) != 40:
        raise FetchError(f"invalid HEAD sha for {ref.org}/{ref.repo}@{default_branch}")
    return default_branch, sha


async def _download_tarball(client: httpx.AsyncClient, ref: GithubRef, branch: str) -> bytes:
    """Stream the tarball with a hard size cap."""
    url = f"https://codeload.github.com/{ref.org}/{ref.repo}/tar.gz/refs/heads/{branch}"
    async with client.stream("GET", url, headers=await _auth_headers()) as response:
        response.raise_for_status()
        buf = bytearray()
        async for chunk in response.aiter_bytes():
            buf.extend(chunk)
            if len(buf) > MAX_TARBALL_BYTES:
                raise TarballTooLargeError(
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
            try:
                archive.extract(extracted_member, destination, filter="data")
            except (OSError, ValueError) as exc:
                # A member whose name is illegal on the local filesystem (e.g. a
                # `?` / `:` / trailing `…` on Windows → WinError 123) or rejected
                # by the tar `data` filter must NOT abort the whole repo extraction.
                # Skip just this file (near-always a binary the scanner ignores) and
                # record it as skipped — otherwise the OSError bubbles out as a
                # `transient` failure and burns 3 retries re-downloading the repo.
                logger.warning(
                    "extract_tarball.member_skipped",
                    member=member.name,
                    error=str(exc)[:200],
                )
                skipped.append(member.name)
                continue
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


class IndexBudget:
    """The ONE per-repo in-memory-index bounds policy both fetch paths share.

    Sticky: once either bound (file count / total bytes) trips, every later
    file is rejected — no best-fit backfill — mirroring the original trees-path
    loop. Inputs MUST arrive in sorted-path order (deterministic,
    fetch-path-independent) and already per-file-capped, so the kept fileset is
    identical regardless of which path fetched the repo.
    """

    def __init__(self, *, max_files: int, max_total_bytes: int) -> None:
        self._max_files = max_files
        self._max_total_bytes = max_total_bytes
        self._kept = 0
        self._total_bytes = 0
        self.bounds_hit = False

    def admit(self, size: int) -> bool:
        if (
            self.bounds_hit
            or self._kept >= self._max_files
            or self._total_bytes + size > self._max_total_bytes
        ):
            self.bounds_hit = True
            return False
        self._kept += 1
        self._total_bytes += size
        return True


def select_index_within_bounds(
    sized_paths: Iterable[tuple[str, int]],
    *,
    max_files: int,
    max_total_bytes: int,
) -> tuple[list[str], list[str]]:
    """Partition pre-sorted, per-file-capped `(path, size)` pairs by the budget.

    Returns `(kept_paths_in_order, skipped_paths)`. Used by the trees path
    (sizes known up-front from the tree listing); the walk path streams bytes
    through the same `IndexBudget` in `collect_bounded_index`.
    """
    budget = IndexBudget(max_files=max_files, max_total_bytes=max_total_bytes)
    kept: list[str] = []
    skipped: list[str] = []
    for path, size in sized_paths:
        (kept if budget.admit(size) else skipped).append(path)
    return kept, skipped


def collect_bounded_index(
    walked: Iterable[tuple[str, bytes]],
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Apply the per-repo index bounds to a (pre-sorted) walked file stream.

    The tarball/walk-path twin of the trees path's bound: consumes the walk
    generator one file at a time, so an over-budget repo costs at most the kept
    budget + one in-flight file of RAM — never the whole uncompressed tree (the
    25 MiB tarball cap is compressed-stream only). Per-file oversize is a belt
    here (`_extract_tarball` already drops > 5 MiB members).
    """
    settings = get_settings()
    budget = IndexBudget(
        max_files=settings.scan_max_index_files,
        max_total_bytes=settings.scan_max_index_total_bytes,
    )
    kept: list[tuple[str, bytes]] = []
    skipped: list[str] = []
    for path, content in walked:
        if len(content) > MAX_PER_FILE_BYTES:
            skipped.append(path)
            continue
        if budget.admit(len(content)):
            kept.append((path, content))
        else:
            skipped.append(path)
    if budget.bounds_hit:
        logger.warning(
            "collect_bounded_index.bounds_hit",
            kept=len(kept),
            skipped=len(skipped),
            max_files=settings.scan_max_index_files,
            max_total_bytes=settings.scan_max_index_total_bytes,
        )
    return kept, skipped


async def fetch_file_index_via_trees(
    github_url: str,
    *,
    ref_sha: str,
    default_branch: str,
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """List the repo tree at `ref_sha` + download every blob ≤ 5 MiB (large-repo path).

    The tarball path fails a monorepo / `awesome-*` collection that blows the
    25 MiB single-stream cap. Instead: one `git/trees?recursive=1` REST call
    (pinned to the resolved HEAD SHA, off the per-repo crawl budget) enumerates
    the tree, then each blob ≤ `MAX_PER_FILE_BYTES` is fetched from
    `raw.githubusercontent.com` (pinned to the SHA → reproducible; off the REST
    rate limit), bounded by a concurrency semaphore.

    Returns `(file_index, skipped_oversized)` with the SAME contract as
    `walk_files`: `file_index` is `list[(path, bytes)]`; `skipped_oversized`
    lists every path dropped for exceeding the per-file cap (parity with
    `_extract_tarball`'s > 5 MiB skip) or for falling past the per-repo bounds
    (`scan_max_index_files` / `scan_max_index_total_bytes`, applied in
    sorted-path order — the same budget + order as the walk path, so the kept
    fileset is fetch-path-independent). A truncated tree (>100k entries / 7 MB)
    raises `FetchError` — fail honestly rather than silently under-scan.
    """
    ref = parse_github_url(github_url)
    settings = get_settings()
    timeout = httpx.Timeout(FETCH_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        # One identity for the whole repo — the tree list + every blob share the
        # same headers (the SHA pins reproducibility, not the token), so build
        # them once rather than per blob.
        auth_headers = await _auth_headers()
        tree_response = await client.get(
            f"https://api.github.com/repos/{ref.org}/{ref.repo}/git/trees/{ref_sha}",
            params={"recursive": "1"},
            headers=auth_headers,
        )
        if tree_response.status_code == 404:
            raise FetchError(f"tree not found: {ref.org}/{ref.repo}@{ref_sha}")
        tree_response.raise_for_status()
        body = tree_response.json()
        if body.get("truncated") is True:
            raise FetchError(
                f"git tree truncated for {ref.org}/{ref.repo}@{ref_sha} "
                "(>100k entries / 7 MB) — cannot scan completely"
            )

        skipped: list[str] = []
        sized: list[tuple[str, int]] = []
        for entry in body.get("tree", []):
            if entry.get("type") != "blob":
                continue
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                continue
            size = entry.get("size") or 0
            if size > MAX_PER_FILE_BYTES:
                skipped.append(path)  # parity with _extract_tarball's > 5 MiB skip
                continue
            sized.append((path, size))

        # Sorted-path order BEFORE the budget — the walk path enumerates in the
        # same order, so the kept fileset is identical regardless of fetch path.
        sized.sort(key=lambda pair: pair[0])
        kept, over_bounds = select_index_within_bounds(
            sized,
            max_files=settings.scan_max_index_files,
            max_total_bytes=settings.scan_max_index_total_bytes,
        )
        skipped.extend(over_bounds)

        if over_bounds:
            logger.warning(
                "fetch_file_index_via_trees.bounds_hit",
                github_url=github_url,
                kept=len(kept),
                skipped=len(skipped),
                max_files=settings.scan_max_index_files,
                max_total_bytes=settings.scan_max_index_total_bytes,
            )

        semaphore = asyncio.Semaphore(settings.scan_trees_fetch_concurrency)

        async def _fetch_blob(path: str) -> tuple[str, bytes]:
            raw_url = (
                f"https://raw.githubusercontent.com/{ref.org}/{ref.repo}/{ref_sha}/{quote(path)}"
            )
            async with semaphore:
                resp = await client.get(raw_url, headers=auth_headers)
            resp.raise_for_status()
            return (path, resp.content)

        file_index = list(await asyncio.gather(*[_fetch_blob(p) for p in kept]))

    return file_index, skipped


def walk_files(directory: Path) -> Iterator[tuple[str, bytes]]:
    """Yield `(relative_path, content_bytes)` for every file in `directory`.

    Sorted-path order (by the posix relative path) — the same deterministic
    order the trees path applies before its budget, so `collect_bounded_index`
    keeps an identical fileset regardless of fetch path.
    """
    paths = sorted(
        (path.relative_to(directory).as_posix(), path)
        for path in directory.rglob("*")
        if path.is_file()
    )
    for rel_posix, path in paths:
        try:
            yield (rel_posix, path.read_bytes())
        except OSError:
            continue
