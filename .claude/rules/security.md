# Security Rules (Core Principles)

These rules apply to ALL code. Auth-specific implementation details land in `security-auth.md` (deferred; written when Track E ships in W5).

## Single-tenant public service (W1)

SaferSkills is a public, free, read-only catalog. **Every endpoint is unauthenticated and reads only the public catalog at W1.** There are no users, no organizations, no tenants, no RLS, no per-request scoping. The public posture IS the security boundary — assume every request is anonymous and adversarial.

- **No write endpoints** at W1 beyond the maintainer-controlled scan pipeline (CI-driven, not user-driven).
- **No user data** at W1. Email-capture lands in W5 with auth; until then `RESEND_*` env vars are used only for outbound transactional sends (e.g. release announcements), never to receive PII.
- Authentication arrives with Track E in W5. When auth lands, this section gains the per-user containment rules (cf. `openlatch-platform/.claude/rules/security.md` § "Per-Organization Containment" for the precedent shape — adapt to single-account, not multi-tenant).

## Vendor-data isolation

Scan inputs and outputs have distinct retention tiers — never conflate them.

| Tier | Examples | Retention | Deletion contract |
|---|---|---|---|
| **Public + indefinite** | Scan results (scores, findings, rule_ids, rubric version); user-submitted GitHub URLs that resolved to a scannable artifact | Indefinite | Public log — transparency over erasure. Vendor right-of-reply per `vendor-appeals.md`. |
| **Stored public artifact snapshots** | Verbatim bytes of scanned **text** files at the scanned ref (`artifact_blobs`, content-addressed dedup; `scans.file_hashes` maps `{path → sha256\|null}`). Binaries/oversize recorded as present-but-not-stored (null). Backs line-level version diffs + the served `.zip`. Public uploads land here too — the "already-public GitHub content" justification extends to "user chose to publish" for an uploaded artifact submitted as `public`. | Indefinite (immutable per scan) | Public reproduction of public/published content. Deletion only via vendor-appeals (github) or the operator runbook (abusive public upload, `vendor-appeals.md`), which clears the scan's `file_hashes` references; unreferenced blobs are swept later (see `database.md`). |
| **Unlisted upload bytes** | Per-run verbatim upload bytes for an **unlisted** scan (`upload_files`, per `scan_run_id`, NO dedup; `content` NULL = binary/oversize). Reachable only via the unguessable `share_token` (`/scans/r/<token>`), never the public catalog. | Transient — 90-day `expires_at` | User-chosen private share. Auto-deleted by the expiry sweep (`app/core/sweeps.py`, lock `0x5AFE5C12`) via `delete_run_cascade`; or eagerly by token-delete (`DELETE /scans/r/<token>`); or the operator runbook. See `database.md` § Upload + visibility. |
| **Private + deletable** | Email addresses (W5+), magic-link tokens, scan-request submitter IPs | Until user deletes via `/account/delete` (W5+) | Hard delete within 30 days of request. |
| **Operational** | Server logs, Sentry events, PostHog telemetry | 30 days (logs) / 90 days (Sentry/PostHog) | Auto-expire. No PII per `telemetry.md`. |

Public-tier data (including stored snapshots) is **never** retroactively scrubbed except via the vendor-appeals workflow (`vendor-appeals.md`).

## Secrets Management

1. **Never commit secrets** — `gitleaks` pre-commit hook enforced.
2. **No secrets in env vars checked into VCS** — `.env.example` with placeholders only. See `environment-config.md`.
3. **No secrets in Docker images** — use Fly secrets / Docker secrets / bind mounts.
4. **No secrets in logs** — auto-redact at logger config level.
5. **No secrets in scan-result payloads** — if a scanned artifact contains a credential-shaped string, the finding records `rule_id` + position + the redacted hash, NEVER the raw secret.
   - **Exception — stored public artifact snapshots are verbatim.** `artifact_blobs` stores the unredacted bytes of scanned text files (Phase B). This is deliberate: the bytes are already public on GitHub at the scanned ref, so storing them is reproduction of already-public data, not new disclosure. If a vendor publicly committed a secret, it is already exposed on GitHub; the remedy is the vendor-appeal deletion path (the stored-snapshot retention tier), not redaction at our boundary. **This exception applies ONLY to the stored-snapshot feature — the scan *trace* invariant in #5 / § Scan-trace transparency is unchanged.**

## Dependency Security

- **Dependabot** drives weekly bumps across every ecosystem (npm root + pip `services/api` + pip `tools/e2e` + docker + github-actions). Grouped by update-type so the PR queue stays small.
- **pip-audit** + **pnpm audit** in CI (lanes 12 / `dep-scan`).
- **Bandit** SAST for Python.
- **Trivy** container scan (CRITICAL/HIGH) on every PR.
- **CodeQL** via GitHub default-setup.
- **OpenSSF Scorecard** weekly via `scorecard.yml`.
- License compliance: Apache 2.0, MIT, BSD, ISC allowed. GPL/AGPL blocked. Verified in CI.

## Audit Trail

Every maintainer-facing mutation MUST emit an audit record. At W1 the surface is mostly read-only, so this covers: scan-pipeline invocations, rubric edits via PR, and vendor-appeal lifecycle transitions. Expand when auth lands.

## Scan-trace transparency

Every scan emits a per-finding trace: which `rule_id` fired, which rubric version was active, what input bytes (hashed) the rule saw. **Hard rule: traces NEVER contain raw artifact payload** (skill bodies, MCP tool descriptions, hook commands). Only hashes, positions, rule_ids, severity. The trace blob is bounded to ~4 KB per finding; deviations need a security review. This is the legal-defense artifact for the vendor right-of-reply (`vendor-appeals.md`) — a vendor must be able to reproduce the finding from the trace alone, without the platform replaying their content.

This is **orthogonal to** the stored-snapshot feature (§ Vendor-data isolation → stored public artifact snapshots) **and to uploads**. Snapshots (and `upload_files`) store verbatim bytes on purpose (to render diffs + serve a zip); the trace stores only hashes/positions/rule_ids. An uploaded artifact is scanned by the same engine and produces the same no-raw-payload trace — the upload front-end changes where the bytes are stored, never what the trace contains. The stores are separate from the trace with separate contracts — never fold raw payload into a trace, and never treat a snapshot/upload as a trace.

## Public-input handling

Every user-submitted GitHub URL is treated as untrusted:

1. **Validate** against `^https://github\.com/[^/]+/[^/]+(/.*)?$` before any fetch.
2. **No SSRF**: every outbound fetch is enforced at the HTTP-client layer with the same private/link-local denylist (`127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `::1`). Three host classes:
   - **User-input-derived** (the scanned repo): go only to `api.github.com` and `raw.githubusercontent.com`.
   - **Ingestion adapters** (host is config-driven, never request-derived): each adapter's `_SSRFTransport` enforces a per-adapter allowlist drawn from the YAML `hosts:` list. The closed set across all adapters: `api.github.com`, `raw.githubusercontent.com` (scan engine + ingestion), `api.npmjs.org`, `replicate.npmjs.com`, `registry.npmjs.com` (npm), `pypi.org` (PyPI), `registry.modelcontextprotocol.io` (MCP Registry), `mcp.so`, `smithery.ai`, `glama.ai`, `pulsemcp.com`, `clawhub.dev`, `skillsmp.com`, `skills.sh`, `claudeskills.info`, `skillhub.club` (aggregator scrapers, Phase B). **A new ingestion source = a new host added here + the YAML `hosts` list + the adapter PR reviewed together (D-04-30).** The `validate` CI lane (`scripts/validate-outbound-allowlist.cjs`) greps adapter files for outbound hosts and asserts every host matches this allowlist.
   - **Server-initiated to a fixed, non-user-controlled URL** — outside the SSRF concern (compile-time-constant host, never reachable from request input): `api.github.com` (the `github_stars` proxy) and `challenges.cloudflare.com` (the Turnstile `siteverify` gate, #10).
3. **Size cap** every fetch (artifacts > 25 MiB rejected up front; per-file > 5 MiB skipped with a logged finding).
4. **No content execution** — scanned artifacts are parsed as data, never imported, eval'd, or shelled.
5. **Per-IP submit cap** — `POST /api/v1/scans` enforces a per-IP daily limit (`SCAN_SUBMIT_DAILY_LIMIT`, default 10; D-FE-11). **Loopback callers are exempt** (`scans.py::_is_loopback` over `_peer_host`): loopback is the operator's own machine — the trusted maintainer/seed path. The **exemption** always keys on `request.client.host` (the real TCP peer, unspoofable to loopback from a remote client); public traffic on Fly arrives over the 6PN proxy and is never loopback, so real submitters are always capped. The **rate-limit bucket key** is `scans.py::_rate_limit_ip` — the peer by default, or the left-most `X-Forwarded-For` on a secret-matched proxy request (see #11). The two are deliberately split: a spoofed `X-Forwarded-For: 127.0.0.1` can never grant the loopback exemption.
6. **Per-IP download cap + size cap** — `GET /api/v1/items/{slug}/download` serves a stored snapshot as a `.zip`; it enforces a per-IP daily limit (`ARTIFACT_DOWNLOAD_DAILY_LIMIT`, default 200; same loopback exemption) and rejects (413) any snapshot whose uncompressed total exceeds the 25 MiB cap. The zip is built in `asyncio.to_thread` so the CPU-bound work never blocks the event loop. Snapshots are immutable → `Cache-Control: public, max-age=31536000, immutable`.
7. **Per-IP unlisted-lookup cap (no oracle)** — `GET /api/v1/scans/r/{token}` (view an unlisted run) enforces a per-IP daily limit (`PRIVATE_LOOKUP_DAILY_LIMIT`, default 60; same loopback exemption, bucket `private_lookup`). Invalid / expired / deleted / not-unlisted tokens all return a **generic 404** — no oracle that distinguishes "wrong token" from "expired". A promoted (now-public) run returns `307` to `/api/v1/scans/runs/<run_id>`. `DELETE /scans/r/{token}` (eager self-delete), `POST /scans/r/{token}/promote` (one-way unlisted→public), and `GET /scans/r/{token}/download` (token-gated `.zip` of the unlisted run's bytes via the storage-split resolver — the public `/items/<slug>/download` 404s for shadow rows) all share the same token surface, the same `private_lookup` cap, the same generic-404 contract, and the same anti-leakage headers (#9). The token route on `/scans/<run_id>` is also blocked at the webapp layer: `/scans/[id].astro` 404s any `visibility='unlisted'` run so an unlisted report is never rendered (indexable) off its capability URL.
8. **Uploaded artifacts are untrusted** — `POST /api/v1/scans/upload` (multipart) shares the `scan_submit` per-IP bucket (loopback exempt). It accepts **one file, one `.zip`, or N loose files** (each multipart part named `file`); the body is read via **streaming** (`request.stream()` + `python_multipart` `MultipartParser`, never `request.form()`) with a 10 MiB hard cap (`UPLOAD_MAX_BYTES`) that is **cumulative across ALL parts combined** (the parser's running byte tally, not per-part). `app/scan/upload.py::extract_upload` branches on part count: one part → the single-file / `.zip` path; N parts → a loose batch scanned like a repo subtree (sanitized relative paths preserved via the shared `_safe_relpath`). Both enforce an extension allowlist + magic-byte/binary check; the multi-file batch additionally forbids archives (`nesting`, no archive-in-batch), sanitizes each part path (`zip_slip`/`bad_path`), and dedups by casefold (`dup_path`) — reusing the audited zip containment, **no new error code**. Bucketed errors: `413 upload_too_large`, `415 unsupported_type|binary_not_allowed`, `422 archive_rejected` (reason ∈ `too_big`,`ratio`,`entries`,`nesting`,`zip_slip`,`bad_path`,`dup_path`). Same no-content-execution rule as #4 — uploads are parsed as data.
9. **Capability-URL anti-leakage** — the unlisted `share_token` must not leak. **Primary** defense is page-level (the `/scans/r/<token>` page sets `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex,nofollow`, `Cache-Control: private,no-store`); the API sets the same headers as **defense-in-depth**. **Token redaction**: `app/core/log_redaction.py` installs a logging filter rewriting `/scans/r/<token>` → `/scans/r/<redacted>` on the `uvicorn.access` + root loggers, and the backend Sentry `before_send=scrub_sentry_event` (`app/observability/events.py`) redacts the token in `event.request.url` + breadcrumb urls. The **webapp** Sentry mirrors this — `webapp/src/lib/observability.ts::redactCapabilityToken` rewrites `/scans/r/<token>` → `/scans/r/<redacted>` in `beforeSend` (`event.request.url`) + `beforeBreadcrumb` urls. The webapp `Base.astro` `noindex` prop additionally suppresses the token-bearing `canonical` + `og:url` so the secret never lands in shareable page source. Every public catalog query hard-filters `visibility='public'`, so unlisted shadow slugs 404 on `/items/<slug>` (+ `/diff` + `/download`).
10. **Human-verification gate (Cloudflare Turnstile)** — both scan-submit endpoints (`POST /api/v1/scans` + `POST /api/v1/scans/upload`) require a Turnstile token, verified server-side against `challenges.cloudflare.com` (`app/services/turnstile.py::verify_turnstile`) **before any scan work** — this **complements, not replaces** the per-IP rate limit (#5), raising the cost of distributed/bot abuse where each accepted submission costs a full scan. Token transport is a custom request header `Cf-Turnstile-Response` (kept out of the scan DTO; lets the upload endpoint reject a bot **before** streaming the multipart body). **Verify precedes the rate-limit, the idempotency-cache lookup, and (for repo scans) the URL-validation parse** — a tokenless bot can neither farm a cached public run nor probe URL validation. **Loopback callers (trusted seed) are exempt** — same `_is_loopback` exemption as #5. **Degradation:** no secret key (`TURNSTILE_SECRET_KEY` unset) → verify bypasses (dev/test/CI), but the `config.py` startup guard **hard-fails boot** in `staging`/`production` so this never happens on a real deploy; secret set but Cloudflare unreachable → **fail-closed** (`False`), a blip must not open the gate. Failure returns `403 {"error":"captcha_failed"}` (the bucketed shape the frontend `mapUploadError` parses). See `environment-config.md` `TURNSTILE_SECRET_KEY` / `PUBLIC_TURNSTILE_SITE_KEY`.
11. **Same-origin API proxy + trusted-proxy client-IP** — the browser calls the backend only same-origin via the webapp's in-app reverse proxy (`webapp/src/pages/api/[...path].ts`, see `frontend-patterns.md` § Same-origin API proxy); there is **no CORS surface for the browser** and no cross-origin API URL baked into the bundle. The proxy strips hop-by-hop headers, passes `Cf-Turnstile-Response` through, and sets `X-Forwarded-For` to the real visitor from a **trusted source only** — `Fly-Client-IP` (which the Fly edge overwrites with the actual client) else the TCP peer, **never the client-supplied `X-Forwarded-For`** (it strips both inbound `X-Forwarded-For` and `Fly-Client-IP` before setting its own, so a forged value cannot reach the backend even partially). When `SAFERSKILLS_PROXY_SHARED_SECRET` is configured it also sets an `X-Proxy-Secret` header (via `set`, overwriting any client value, so a browser can neither inject nor read it). Because the proxy hop replaces the TCP peer the backend sees, the per-IP caps (#5/#6/#7) read the visitor from XFF **only on a request whose `X-Proxy-Secret` matches `SAFERSKILLS_PROXY_SHARED_SECRET`** (constant-time, `scans.py::_rate_limit_ip`). This is what lets the **API stay publicly reachable** (e2e + the data-seed CLI hit it directly) without a spoof hole: a direct caller cannot forge the secret, so its `X-Forwarded-For` is ignored and it is capped on its real peer; legitimate direct callers simply fall back to the peer. Unset secret (dev/test/CI) → raw peer, no spoof surface. The loopback exemption is never XFF-derived (#5). The secret must be **identical on the webapp app and the API app** (both staged in `deploy.yml`); rotate by setting a new value on both in one deploy.

## When to update this rule

| Change | Updates here |
|---|---|
| Auth lands (Track E W5) | Replace "Single-tenant public service" with the per-user containment rules; add `security-auth.md` cross-ref |
| New retention tier or deletion endpoint | "Vendor-data isolation" table |
| New SAST / dependency scanner / Scorecard probe change | "Dependency Security" |
| New scan-trace field | "Scan-trace transparency" — re-verify the no-raw-payload invariant |
| New stored-snapshot field / store | "Vendor-data isolation" stored-snapshots tier + `database.md` + re-verify the trace stays no-raw-payload |
| New upload store / unlisted retention change | "Vendor-data isolation" unlisted-upload tier + "Public-input handling" #8 + `database.md` |
| New outbound host allowed | "Public-input handling" #2 + the HTTP-client allowlist |
| CAPTCHA / human-gate change | "Public-input handling" #10 + `app/services/turnstile.py` + `config.py` startup guard + `environment-config.md` |
| Rate-limit scope / exemption change | "Public-input handling" #5/#6/#7 + `scans.py::_is_loopback` / `_rate_limit_ip` + `environment-config.md` |
| Same-origin proxy / trusted-proxy-secret change | "Public-input handling" #11 + `webapp/src/pages/api/[...path].ts` + `scans.py::_rate_limit_ip` + `SAFERSKILLS_PROXY_SHARED_SECRET` in `environment-config.md` + `deploy.yml` (staged on both apps) |
| Upload validation / zip-safety / token-redaction change | "Public-input handling" #8/#9 + `app/scan/upload.py` + `app/core/log_redaction.py` |
| Access-log writer / IP-redaction change | `privacy.md` + `app/core/access_log_middleware.py` (redact at write time; never store raw IP) |
