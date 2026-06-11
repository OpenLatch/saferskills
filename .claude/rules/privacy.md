# Privacy

Always-on rule. Controller = OpenLatch EU / France (CNIL). Privacy contact: `privacy@openlatch.ai`. Public disclosure lives in `webapp/src/pages/privacy.astro`.

## Controller and legal basis

- **Controller**: OpenLatch, registered in France. Lead supervisory authority: CNIL (`www.cnil.fr`). No statutory DPO required.
- **Legal basis**: legitimate interest (Art. 6(1)(f) GDPR) for security research, abuse prevention, and service improvement. Consent basis applies only to the newsletter (not yet active).
- **Cookieless-by-design**: PostHog runs in cookieless mode (EU region). No tracking cookies, no persistent device identifiers, no cookie-consent banner required.

## `access_log` table (I-04 Phase A)

The `access_log` table records anonymised, aggregate catalog-access signals for the I-06 B2B intelligence feature. It is a **write-only** store at I-04; the reader ships in I-06.

### What is stored

Closed enum of actions only — `item_view`, `catalog_search`, `catalog_filter`, `install_copy`, `badge_fetch`, `sources_page_view`. No slugs, no query strings, no URLs, no PII in any row.

### IP redaction (mandatory)

**Raw IP addresses are NEVER stored.** The writer middleware (`app/core/access_log_middleware.py`) redacts the IP to `/24` (IPv4) or `/48` (IPv6) AT WRITE TIME — before the row is inserted. No downstream code ever sees a more precise IP. This is enforced at the middleware layer; no override is permitted.

- IPv4 example: `203.0.113.42` → stored as `203.0.113.0/24`
- IPv6 example: `2001:db8:85a3::8a2e:370:7334` → stored as `2001:db8:85a3::/48`

The redaction function lives in `app/core/access_log_middleware.py`. It is called unconditionally — there is no "trusted source" exemption for IP precision.

### Retention

30-day raw-row retention, consistent with the "Operational" tier in `security.md` § Vendor-data isolation. Rows are swept after 30 days. Aggregated rollup stats survive beyond 30 days without row-level IP data.

### No export

Redacted `/24` or `/48` prefixes are never exported raw to third parties. Aggregated analytics (bucketed counts per action per day) may be surfaced in internal dashboards or the I-06 B2B intelligence surface, but the row-level store is internal only.

### Hard rules

1. **Write-only at I-04.** No `access_log` reads in any router, query, or service until I-06 lands the reader.
2. **Redact at middleware layer.** Never pass a raw IP into any `access_log` insert call.
3. **Closed action enum.** New action type = update the enum in `app/core/access_log_middleware.py` + this rule + `privacy.astro`.
4. **No PII fields.** No `user_agent`, no `referer`, no raw `path`, no slug. Only `action`, `redacted_ip`, `timestamp`, and optionally `source_kind` (closed enum) for aggregate faceting.

## `install_events` table (I-05)

The `install_events` table records **anonymous** install reports from the `saferskills`
CLI (D-05-31), powering the real `install_activity` counts on item pages (replacing
the deterministic mock). It is a **new store distinct from `access_log`** — required
because `access_log` is write-only-until-I-06, closed-action, and 30-day-swept, so it
can neither serve the read nor preserve the `all_time` count.

### What is stored

`catalog_item_id` (FK), `agent` (the 8-agent native enum), `kind` (the 5-kind native
enum), `cli_version` (≤32 chars), `redacted_ip`, `created_at`. **No slug-in-clear, no
URL, no PII.** The reported install is anonymous — closed-enum agent + kind only.

### IP redaction (mandatory)

Same contract as `access_log`: the submitter IP is redacted to `/24` (IPv4) or `/48`
(IPv6) **at write time** in `app/routers/installs.py` (via
`access_log_middleware.redact_ip`) — a raw IP is never stored.

### Automatic (no consent), legitimate interest

Reporting is **automatic** — the CLI sends an anonymous install count on every install
(no consent prompt). It rests on the legitimate-interest basis (Art. 6(1)(f) — service
improvement / popularity signals), justified by the anonymity (closed-enum agent + kind,
redacted IP, no slug-in-clear, no PII). It is **suppressed only** by a universal opt-out
(`CI` / `DO_NOT_TRACK` / `SAFERSKILLS_NO_TELEMETRY`) or a source/fork build (no baked key
⇒ inert). It is **independent of** the usage-analytics consent (the `telemetry` config
key / first-run prompt), which gates only the PostHog `command_invoked` event. See
`security.md` § Vendor-data isolation + the CLI `core::telemetry::install_reporting_allowed`.

### Retention

**Retained** (redacted IP, closed-enum, no PII) so the `all_time` aggregate survives
— distinct from `access_log`'s 30-day sweep. A future per-item rollup counter is an
optimization, not required. See `security.md` § Vendor-data isolation.

### No export

Row-level `install_events` are internal; only bucketed aggregates (counts per agent
per window) surface on the public item page.

## agent_scan_telemetry table (I-5.5)

The `agent_scan_telemetry` table records **anonymous, company-level** signals about
who runs an Agent Scan, for the I-06 B2B intelligence feature. It is a **write-only**
store at I-5.5 (the reader ships in I-06), distinct from `install_events`.

### What is stored

Company-level **ASN** + `as_org` + `country` + a **server-derived closed-key
fingerprint** only — plus the `agent_run_id` (FK). **No raw IP, no slug-in-clear, no
URL, no PII.** The ASN/as_org/country are derived from the submitter IP at write time
via the IPinfo Lite MMDB (`IPINFO_LITE_DB_PATH`).

### IP redaction (mandatory)

Same contract as `access_log` / `install_events`: the submitter IP is **redacted at
write time** — the writer **redacts-then-derives** the ASN (redaction precedes ASN
lookup), so a raw IP is never stored. No downstream code ever sees a precise IP.

### Automatic (no consent), legitimate interest

Write-only company-level aggregate signal on the legitimate-interest basis
(Art. 6(1)(f) — security research / service improvement), justified by the anonymity
(closed-key fingerprint + ASN/org/country, redacted IP, no PII, no slug-in-clear).

### Retention

**Retained** (anonymous, no PII) for as long as the run exists. The `agent_run_id`
FK is **`ON DELETE SET NULL`** at the DB layer, but every app-level deletion path
goes through `delete_agent_run_cascade`, which **fully erases** the run's telemetry
rows (unlisted self-delete, expiry sweep, admin delete) — a deliberate full-erase
override of the SET-NULL constraint (see its docstring). Public runs are permanent
(admin-only delete), so their telemetry persists with them.

### No export

Row-level `agent_scan_telemetry` is internal; only bucketed aggregates surface in the
I-06 B2B intelligence surface. No raw ASN/IP export to third parties.

## agent_verify_waitlist table (I-5.6)

The `agent_verify_waitlist` table records demand for the (out-of-scope)
independently-observed verify tier — one row per "Request independent verification"
tile submit on an Agent Report (D-5.6-08), written by
`POST /api/v1/agent-scans/verify-waitlist`.

### What is stored

`email` (OPTIONAL — only when the requester leaves one; the tile is account-free),
`redacted_ip`, `created_at`. **No slug, no URL, no agent name, no PII beyond the
opt-in email.** It is a demand signal, not a profile.

### IP redaction (mandatory)

Same contract as `access_log` / `install_events`: the submitter IP is **redacted at
write time** to /24 (IPv4) or /48 (IPv6) in `app/routers/agent_scans.py` (via
`access_log_middleware.redact_ip`) — a raw IP is never stored.

### Consent + legal basis

The optional email is provided **only when the requester types it** (explicit, an
opt-in contact for the future verify tier — consent basis Art. 6(1)(a) for that
field). The redacted-IP demand row rests on the legitimate-interest basis
(Art. 6(1)(f) — product demand measurement), justified by the redaction + the
absence of other PII.

### Retention

**Retained** (redacted IP + opt-in email only) — the demand signal is the point.
A requester who wants their email erased uses the privacy contact (`privacy@openlatch.ai`).

### No export

Row-level `agent_verify_waitlist` is internal; the email list seeds the future
verify-tier launch only.

## First-launch audit (I-05, D-05-26)

On the install CLI's first interactive run it offers a **one-time, opt-in** security
audit of everything already installed across the user's agents (`scan --local`). On
accept it uploads that installed inventory's content to the API for server-side
scanning; **public by default**, with the prompt letting the user choose a **private
(unlisted)** report instead. The choice is persisted so it never re-prompts; the
audit is skipped (and never prompts) in any non-interactive context
(`--json`/`--quiet`/non-TTY/`--no-input`).

The scanned bytes follow the **existing snapshot/upload retention tiers** — a public
audit lands in the public `artifact_blobs` snapshot tier (indefinite, immutable per
scan); a private audit lands in the per-run `upload_files` tier (90-day `expires_at`,
reachable only via the unguessable `share_token`). No new store, no new retention
rule. See `security.md` § Vendor-data isolation + `database.md` § Upload + visibility.

## Public disclosure

`webapp/src/pages/privacy.astro` is the canonical privacy policy surface. The access_log disclosure section must be kept in sync with this rule. See Section 3 of the policy for the at-a-glance table and the IP-redaction statement.

Link to `security.md` § Vendor-data isolation for the full retention-tier breakdown.

## When to update this rule

| Change | Updates here |
|---|---|
| `install_events` column / retention / enum change | "install_events table" + `app/models/install_event.py` + `app/routers/installs.py` + migration 0014 + `security.md` |
| `agent_scan_telemetry` column / retention / fingerprint change | "agent_scan_telemetry table" + `app/models/agent_scan_telemetry.py` + `app/agent_scan/` + migration 0019 + `security.md` |
| `agent_verify_waitlist` column / retention change | "agent_verify_waitlist table" + `app/models/agent_verify_waitlist.py` + `app/routers/agent_scans.py` (`verify_waitlist`) + migration 0020 + `database.md` |
| New `action` enum value added | "What is stored" + `app/core/access_log_middleware.py` enum + `privacy.astro` |
| IP redaction granularity changed | "IP redaction" + `app/core/access_log_middleware.py` + `privacy.astro` |
| `access_log` reader ships (I-06) | "access_log table" — remove "write-only at I-04" note; document the read surface |
| Retention period changed | "Retention" + `security.md` operational tier |
| New aggregated export surface | "No export" — document the target + legal basis |
| Controller / DPA details change | "Controller" + `privacy.astro` § who-we-are |
