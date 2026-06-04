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

The `install_events` table records **opt-in** install reports from the `saferskills`
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

### Opt-in only

Reporting is **opt-in** (first-run CLI consent; off by default, skipped + off in
non-TTY/CI/`--json`/`--no-input`). A row exists only because a user chose to report.

### Retention

**Retained** (redacted IP, closed-enum, no PII) so the `all_time` aggregate survives
— distinct from `access_log`'s 30-day sweep. A future per-item rollup counter is an
optimization, not required. See `security.md` § Vendor-data isolation.

### No export

Row-level `install_events` are internal; only bucketed aggregates (counts per agent
per window) surface on the public item page.

## Public disclosure

`webapp/src/pages/privacy.astro` is the canonical privacy policy surface. The access_log disclosure section must be kept in sync with this rule. See Section 3 of the policy for the at-a-glance table and the IP-redaction statement.

Link to `security.md` § Vendor-data isolation for the full retention-tier breakdown.

## When to update this rule

| Change | Updates here |
|---|---|
| `install_events` column / retention / enum change | "install_events table" + `app/models/install_event.py` + `app/routers/installs.py` + migration 0014 + `security.md` |
| New `action` enum value added | "What is stored" + `app/core/access_log_middleware.py` enum + `privacy.astro` |
| IP redaction granularity changed | "IP redaction" + `app/core/access_log_middleware.py` + `privacy.astro` |
| `access_log` reader ships (I-06) | "access_log table" — remove "write-only at I-04" note; document the read surface |
| Retention period changed | "Retention" + `security.md` operational tier |
| New aggregated export surface | "No export" — document the target + legal basis |
| Controller / DPA details change | "Controller" + `privacy.astro` § who-we-are |
