"""Dedicated regression guard: an upload scan must reach `completed`.

This is the e2e that would have caught the prod incident where EVERY interactive
/ upload scan died `failed` with nothing persisted — the asyncpg LISTEN/NOTIFY
pool never initialized (a `sslmode=disable` DSN whose `ssl=` form raw asyncpg
rejected), so `scan_runner._emit` raised on the first progress event. Bulk
auto-scanning never touches that pool, so the catalog looked healthy and the
read-only e2e commands stayed green — only a real SUBMIT exercises it. And the
bug is environment-specific (managed `sslmode=disable` Postgres), so it does not
reproduce on a local dev DSN — the test has to submit against the DEPLOYED stack.

So this command submits a tiny upload and POLLS the run to a terminal state,
asserting `status == "completed"` with `capability_count >= 1`. A `failed` (or
never-terminal) run is the exact regression and fails the gate.

**Submit gate — the CLI Proof-of-Work path, not Turnstile.** A deployed env runs a
REAL Turnstile secret (a dummy token 403s), and the loopback exemption only covers
a local stack — neither lets an automated client submit against staging/prod. So
this command uses the same gate the `saferskills` CLI uses: `GET /scans/cli-challenge`
→ brute-force a PoW solution → submit with the `X-SaferSkills-CLI-PoW` header (byte
layout mirrors `app/services/cli_pow.py`). That works wherever the PoW secret is set
(staging + prod). If the PoW endpoint is unavailable (503 — a local dev stack with no
secret), it falls back to a header-less submit (the loopback exemption). Any non-202
(rate cap / unexpected gate / unsubmittable env) → SKIP, like `unlisted-flow`.

Unlisted visibility keeps it out of the public catalog and lets us eagerly delete
the run at the end. Staging acceptance, NOT a required pr-checks lane.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib

import httpx

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.http_client import make_client, request_with_retries
from saferskills_e2e.shared.output import print_fail, print_info, print_ok, print_warn

# A minimal but real SKILL.md — valid frontmatter so discovery yields one skill
# capability (the scored result we assert on).
_FIXTURE = (
    b"---\n"
    b"name: e2e-scan-completes\n"
    b"description: e2e regression fixture asserting an upload scan completes\n"
    b"---\n"
    b"# e2e-scan-completes\n\n"
    b"A tiny skill used only to prove the scan pipeline reaches a scored result.\n"
)

_TERMINAL = frozenset({"completed", "failed"})
_POLL_ATTEMPTS = 40
_POLL_INTERVAL_S = 1.5
# Defensive bound on PoW effort (the server default difficulty is 20 ≈ 1M hashes,
# ~1s in Python). A challenge above this is treated as too costly → skip, mirroring
# the CLI's own difficulty cap so a misconfigured/hostile server can't spin us.
_MAX_POW_DIFFICULTY = 24


def _leading_zero_bits(digest: bytes) -> int:
    """Most-significant leading zero bits of a digest — mirrors `cli_pow.py`."""
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        bits += 8 - byte.bit_length()
        break
    return bits


def _solve_pow(challenge: str, difficulty: int) -> str | None:
    """Brute-force a `solution` so sha256(challenge+solution) clears `difficulty`
    leading zero bits — the exact check `cli_pow.verify_pow` re-runs. ASCII counter
    solutions (never a '.', which would break the header's field split). Returns
    None if the difficulty is implausibly high (defensive)."""
    if difficulty < 1 or difficulty > _MAX_POW_DIFFICULTY:
        return None
    prefix = challenge.encode("ascii")
    max_iters = 1 << (difficulty + 7)  # 128x headroom over the 2^difficulty expectation
    for n in range(max_iters):
        solution = str(n)
        if (
            _leading_zero_bits(hashlib.sha256(prefix + solution.encode("ascii")).digest())
            >= difficulty
        ):
            return solution
    return None


class ScanCompletesCommand(BaseCommand):
    name = "scan-completes"
    description = "Submit an upload scan and assert it reaches status=completed"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()
        async with make_client(config) as client:
            created = await self._submit(client, config)
            if created is None:
                print_warn(
                    "Could not submit an upload scan (cap / gate / unsubmittable env) — skipping."
                )
                return ExitCode.OK
            run_id, token = created
            try:
                return await self._await_completion(client, config, run_id)
            finally:
                await self._cleanup(client, config, token)

    async def _pow_header(self, client: httpx.AsyncClient, config: Config) -> str | None:
        """Fetch + solve a CLI Proof-of-Work challenge → the `X-SaferSkills-CLI-PoW`
        header value `"{challenge}.{solution}"`. None when PoW is unavailable (503 —
        no secret on a local stack) or the difficulty is implausible."""
        try:
            resp = await client.get(f"{config.api_url}/api/v1/scans/cli-challenge")
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None  # 503 (no PoW secret) → fall back to a header-less submit
        body = resp.json()
        challenge = body.get("challenge")
        difficulty = body.get("difficulty")
        if not isinstance(challenge, str) or not isinstance(difficulty, int):
            return None
        solution = await asyncio.to_thread(_solve_pow, challenge, difficulty)
        if solution is None:
            print_info(f"PoW difficulty {difficulty} too high to solve in-test — skipping.")
            return None
        return f"{challenge}.{solution}"

    async def _submit(
        self, client: httpx.AsyncClient, config: Config
    ) -> tuple[str, str | None] | None:
        """POST the fixture upload through the CLI-PoW gate (or header-less on a
        loopback dev stack). Returns (run_id, share_token) on 202, else None (any
        non-202 → graceful skip, matching `unlisted-flow`)."""
        headers: dict[str, str] = {}
        pow_header = await self._pow_header(client, config)
        if pow_header is not None:
            headers["X-SaferSkills-CLI-PoW"] = pow_header
        try:
            resp = await client.post(
                f"{config.api_url}/api/v1/scans/upload",
                files={"file": ("SKILL.md", _FIXTURE, "text/markdown")},
                data={"visibility": "unlisted"},
                headers=headers,
            )
        except httpx.HTTPError as e:
            print_warn(f"upload submit failed at transport level: {e!s}")
            return None
        if resp.status_code != 202:
            print_info(f"upload submit returned {resp.status_code} (expected 202) — skipping.")
            return None
        body = resp.json()
        run_id = body.get("id")
        if not isinstance(run_id, str) or not run_id:
            print_fail("upload 202 response carried no run id")
            return None
        share_url = body.get("share_url") or ""
        token = share_url.rstrip("/").split("/scans/r/")[-1] or None
        print_ok(f"upload accepted — run {run_id[:8]} queued")
        return run_id, token

    async def _await_completion(
        self, client: httpx.AsyncClient, config: Config, run_id: str
    ) -> ExitCode:
        """Poll the run by id (no private-lookup cap on this route) until terminal,
        then assert it COMPLETED with at least one scored capability."""
        url = f"{config.api_url}/api/v1/scans/runs/{run_id}"
        status = "pending"
        capability_count = 0
        for _ in range(_POLL_ATTEMPTS):
            try:
                resp = await request_with_retries(client, "GET", url, retries=config.retries)
            except httpx.HTTPError as e:
                print_fail(f"polling the run report failed: {e!s}")
                return ExitCode.FAIL_UPLOAD_SCAN
            if resp.status_code != 200:
                print_fail(f"run report returned {resp.status_code} while polling")
                return ExitCode.FAIL_UPLOAD_SCAN
            body = resp.json()
            status = body.get("status") or "pending"
            capability_count = body.get("capability_count") or 0
            if status in _TERMINAL:
                break
            await asyncio.sleep(_POLL_INTERVAL_S)

        if status != "completed":
            # The exact regression: the scan never reached a scored result.
            print_fail(
                f"upload scan did not complete (status={status!r}) — the scan pipeline is broken "
                "(e.g. the asyncpg NOTIFY pool failed to initialize)."
            )
            return ExitCode.FAIL_UPLOAD_SCAN
        if capability_count < 1:
            print_fail(f"scan completed but discovered 0 capabilities (count={capability_count})")
            return ExitCode.FAIL_UPLOAD_SCAN

        print_ok(f"upload scan completed with {capability_count} capability(ies)")
        print_info("scan-completes OK")
        return ExitCode.OK

    async def _cleanup(self, client: httpx.AsyncClient, config: Config, token: str | None) -> None:
        """Best-effort eager delete of the unlisted run (never affects the verdict)."""
        if not token:
            return
        with contextlib.suppress(httpx.HTTPError):
            await client.delete(f"{config.api_url}/api/v1/scans/r/{token}")
