# Security Rules (Core Principles)

These rules apply to ALL code. Auth-specific implementation details land in `security-auth.md` (deferred; written when Track E ships in W5).

## Single-tenant public service (W1)

SaferSkills is a public, free, read-only catalog. **Every endpoint is unauthenticated and reads only the public catalog at W1.** There are no users, no organizations, no tenants, no RLS, no per-request scoping. The public posture IS the security boundary — assume every request is anonymous and adversarial.

- **No write endpoints** at W1 beyond the maintainer-controlled scan pipeline (CI-driven, not user-driven).
- **No user data** at W1. Email-capture lands in W5 with auth; until then `RESEND_*` env vars are used only for outbound transactional sends (e.g. release announcements), never to receive PII.
- Authentication arrives with Track E in W5. When auth lands, this section gains the per-user containment rules (cf. `openlatch-platform/.claude/rules/security.md` § "Per-Organization Containment" for the precedent shape — adapt to single-account, not multi-tenant).

## Vendor-data isolation

Scan inputs and outputs have three retention tiers — never conflate them.

| Tier | Examples | Retention | Deletion contract |
|---|---|---|---|
| **Public + indefinite** | Scan results (scores, findings, rule_ids, rubric version); user-submitted GitHub URLs that resolved to a scannable artifact | Indefinite | Public log — transparency over erasure. Vendor right-of-reply per `vendor-appeals.md`. |
| **Private + deletable** | Email addresses (W5+), magic-link tokens, scan-request submitter IPs | Until user deletes via `/account/delete` (W5+) | Hard delete within 30 days of request. |
| **Operational** | Server logs, Sentry events, PostHog telemetry | 30 days (logs) / 90 days (Sentry/PostHog) | Auto-expire. No PII per `telemetry.md`. |

Public-tier data is **never** retroactively scrubbed except via the vendor-appeals workflow (`vendor-appeals.md`).

## Secrets Management

1. **Never commit secrets** — `detect-secrets` pre-commit hook enforced.
2. **No secrets in env vars checked into VCS** — `.env.example` with placeholders only. See `environment-config.md`.
3. **No secrets in Docker images** — use Fly secrets / Docker secrets / bind mounts.
4. **No secrets in logs** — auto-redact at logger config level.
5. **No secrets in scan-result payloads** — if a scanned artifact contains a credential-shaped string, the finding records `rule_id` + position + the redacted hash, NEVER the raw secret.

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

## Public-input handling

Every user-submitted GitHub URL is treated as untrusted:

1. **Validate** against `^https://github\.com/[^/]+/[^/]+(/.*)?$` before any fetch.
2. **No SSRF**: outbound fetches go only to `api.github.com` and `raw.githubusercontent.com`, enforced at the HTTP-client layer (denylist `127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `::1`).
3. **Size cap** every fetch (artifacts > 25 MiB rejected up front; per-file > 5 MiB skipped with a logged finding).
4. **No content execution** — scanned artifacts are parsed as data, never imported, eval'd, or shelled.

## When to update this rule

| Change | Updates here |
|---|---|
| Auth lands (Track E W5) | Replace "Single-tenant public service" with the per-user containment rules; add `security-auth.md` cross-ref |
| New retention tier or deletion endpoint | "Vendor-data isolation" table |
| New SAST / dependency scanner / Scorecard probe change | "Dependency Security" |
| New scan-trace field | "Scan-trace transparency" — re-verify the no-raw-payload invariant |
| New outbound host allowed | "Public-input handling" #2 + the HTTP-client allowlist |
