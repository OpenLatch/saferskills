---
paths:
  - "**/vendor-appeal*"
  - "**/appeal*"
  - ".github/ISSUE_TEMPLATE/04-vendor-appeal*"
  - "services/api/app/appeals/**"
  - "webapp/src/pages/appeal*.astro"
---

# Vendor Appeals — right-of-reply contract

> **Paths**: `**/vendor-appeal*`, `**/appeal*`, `.github/ISSUE_TEMPLATE/04-vendor-appeal*`, `services/api/app/appeals/**`, `webapp/src/pages/appeal*.astro`

## Purpose

Public scan results are a powerful claim. SaferSkills' legitimacy depends on the vendor of every scanned artifact (skill / MCP / hook / plugin) having an effective, transparent, time-bounded right to challenge a finding. **Transparency over erasure** — we never silently delete a finding; we publish the vendor response next to it.

## Submission paths

| Path | Status | When to use |
|---|---|---|
| **GitHub issue template** (`.github/ISSUE_TEMPLATE/04-vendor-appeal.yml`) | Live | Default path. Tracks the appeal in a public issue, links the catalog item, captures structured fields (rule_id, scan timestamp, rebuttal). |
| **Right-of-reply web form** (`/items/<slug>/respond`) | **Live** | The friction-minimizing structural right-of-reply. Verify-by-`.saferskills/verify.txt` → HttpOnly `ss_vendor_session` cookie (webapp-owned; the API mints + is the sole verifier of the HS256 JWT) → ≤2000-char Markdown response posted to `POST /api/v1/items/<slug>/vendor/responses`, rendered publicly next to findings. Optional immediate re-scan. GitHub issues remain the fallback. |
| **Appeal web form** (`/appeal` on `saferskills.ai/appeal`) | **Planned** | The formal finding-appeal flow (distinct from the right-of-reply above). Ships with `webapp/src/pages/appeal.astro`. Posts to `POST /api/v1/appeals` (planned endpoint). |
| **Email** (`appeals@openlatch.ai`) | Live | Human-escalation path when the GitHub form is insufficient (e.g. private-disclosure-of-sensitive-detail). Email is converted to a public issue by a maintainer unless the vendor explicitly requests private handling. |

## Identity verification

A vendor's identity is verified one of two ways — both are sufficient on their own, neither requires platform-side account creation:

1. **`.saferskills/verify.txt`** in the scanned repo, containing the verifier's GitHub username on its own line. Mirrors the well-known DNS-verification pattern; survives repo forks because we check the canonical scanned URL.
2. **Email-from-maintainer**: the appeal arrives from an email address that matches the repo's public maintainer record (GitHub `Email` field on the user, or `maintainers` block in the artifact manifest).

A maintainer team member verifies in the issue thread; the verification check is publicly logged.

## Public response — transparency over erasure

Every appeal becomes a **public comment on the catalog item**, even after a re-scan.

- If the appeal succeeds (the finding is judged invalid or the rule misfired): the finding is annotated with the appeal outcome and rationale, AND the rubric is updated if the rule itself needs adjustment. The original finding stays in the public scan history with a clear "appealed and resolved" marker.
- If the appeal fails (the finding stands): the appeal text is published next to the finding with a substantive maintainer response. The vendor's argument is heard publicly.
- **Findings are never silently deleted.** The audit trail is the legitimacy artifact — if we deleted findings on appeal, every vendor would suspect every other appealed finding was removed.

## 1-hour re-scan SLA

A verified appeal triggers an **immediate re-scan**. The maintainer team commits to publishing the updated score within **1 hour** of verified-appeal acknowledgment.

- The re-scan runs against the artifact at the exact commit SHA the appeal references (or the current HEAD if no SHA is supplied).
- The re-scan response carries both the new score AND a delta against the prior score.
- Missing the 1-hour SLA is a public incident — the team logs the delay in the appeal thread with a rationale.

## Banned reasons for rejection

Maintainers MAY NOT reject an appeal with any of these as the substantive reason:

- "We already cover this." A reasonable rebuttal must be re-addressed; "already covered" is not a substantive response.
- "The rule is correct." If the rule is correct, explain why the vendor's argument fails on the merits of the rule's documented trigger.
- "You can't appeal this rule." Every rule is appealable. Period.
- "Insufficient evidence" without naming what evidence would have sufficed.

Every appeal gets a **substantive public response** that engages the vendor's specific argument.

## Appeal lifecycle (states)

| State | Trigger | SLA |
|---|---|---|
| `submitted` | Issue / form / email received | — |
| `identity_verified` | One of the two verification paths confirmed | Within 24h business |
| `under_review` | Maintainer assigned + investigation started | — |
| `rescan_triggered` | Re-scan job kicked off | Within 1h of `identity_verified` |
| `resolved_upheld` | Finding stands; substantive response published | Within 5 business days of `identity_verified` |
| `resolved_overturned` | Finding overturned; catalog updated | Within 5 business days of `identity_verified` |
| `resolved_rule_changed` | Rule itself amended via the RFC workflow (`methodology.md`) | Bounded by the RFC 7-day window |

Each state transition is an audit event (cf. `security.md` § "Audit Trail").

## Uploaded artifacts — no right-of-reply

The right-of-reply above is a **vendor** contract — it presumes a scanned artifact with a discoverable upstream owner (a GitHub repo). **Directly uploaded artifacts have NO vendor right-of-reply**: there is no repo to verify ownership against (`.saferskills/verify.txt`), no upstream maintainer record, and no auto-rescan path.

- **Unlisted uploads** self-delete via `DELETE /api/v1/scans/r/{token}` (the submitter holds the only link) and auto-expire after 90 days — no appeal needed.
- **Public uploads** are the only case requiring a removal path. The only such path is the manual SQL **operator runbook** at `contributor-docs/runbooks/operator-upload-deletion.md`, which deletes the run via `delete_run_cascade(..., allow_public=True)`. There is **no** new takedown endpoint, **no** automated takedown, and **no** Slack alert — abusive-public-upload removal is a deliberate manual operator action.

## Escalation — `appeals@openlatch.ai`

The email inbox is for cases the GitHub form cannot serve:

- Vendor needs to disclose CVE-eligible detail privately.
- Vendor is a real person who cannot use GitHub for the appeal.
- Vendor is contesting an identity-verification result.

The inbox is monitored by the maintainer team. Replies move the appeal back to a public issue unless the vendor explicitly requests continued private handling AND the maintainer team agrees private handling is necessary (rare; the default is public).

## Hard rules

1. **Public response.** Every appeal gets a substantive public response on the catalog item.
2. **No silent deletes.** Findings stay in public history with appeal markers — never removed.
3. **Identity verification before re-scan.** No re-scan triggers from an unverified appeal.
4. **1-hour re-scan SLA** post-verification.
5. **Substantive responses only.** The banned-reasons list is non-negotiable.
6. **Audit-log every state transition.**

## When to update this rule

| Change | Updates here |
|---|---|
| New submission path (e.g. a Discord channel formalized) | "Submission paths" table |
| New identity-verification path | "Identity verification" |
| New lifecycle state | "Appeal lifecycle" table + the audit event + `security.md` |
| SLA change | "1-hour re-scan SLA" — re-verify whether SLA is still operationally feasible |
| Appeal web form ships | Move its status to Live + add `services/api/app/appeals/**` to the paths block |
| Banned-reason added | "Banned reasons for rejection" |
| Upload removal path changes (e.g. an automated takedown lands) | "Uploaded artifacts — no right-of-reply" + `contributor-docs/runbooks/operator-upload-deletion.md` |
