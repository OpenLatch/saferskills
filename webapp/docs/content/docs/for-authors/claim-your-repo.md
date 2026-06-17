---
title: "Claim Your Repo & Right of Reply"
description: "Prove repo ownership with .saferskills/verify.txt or maintainer email, then post a public reply that triggers a 1-hour re-scan."
updated: 2026-06-16
---
To respond to a finding on your scanned repo, prove ownership one of two ways — commit a `.saferskills/verify.txt` file containing your GitHub username, or appeal from an email that matches the repo's public maintainer record — then post your reply at `/items/<slug>/respond`. A verified reply is published publicly next to the finding and triggers an immediate re-scan with a one-hour SLA. Findings are never silently deleted; they are annotated with the appeal outcome.

## How do I prove I own the repo?

You prove ownership one of two ways, and either one is sufficient on its own — neither requires creating an account:

1. **`.saferskills/verify.txt`** — commit a file at `.saferskills/verify.txt` in the scanned repo containing your GitHub username on its own line. This mirrors the well-known DNS-verification pattern and survives forks, because SaferSkills checks the canonical scanned URL, not a copy.
2. **Maintainer email** — submit your reply from an email address that matches the repo's public maintainer record (the GitHub `Email` field on the user, or the `maintainers` block in the artifact manifest).

A maintainer-team member confirms the verification, and that check is publicly logged. Verification happens before any re-scan — an unverified reply never triggers one.

## How do I post a reply?

Once you can verify ownership, go to `/items/<slug>/respond` for your capability and submit a Markdown response of up to 2000 characters. Verifying by `.saferskills/verify.txt` issues you a short-lived vendor session; your response is then posted to `POST /api/v1/items/<slug>/vendor/responses` and rendered publicly next to the findings. You can opt into an immediate re-scan at the same time. If the web form does not fit your case — for example you need to disclose a CVE-eligible detail privately — the GitHub issue template and the `appeals@openlatch.ai` inbox remain as fallbacks.

## What happens after I reply — and is the finding removed?

Your reply is published, and the finding stays. SaferSkills' rule is **transparency over erasure**: a verified, accepted appeal annotates the finding with the outcome and rationale and updates the rubric if the rule itself needs adjustment — but the original finding remains in the public scan history with a clear "appealed and resolved" marker. If the finding stands, your appeal text is published next to it with a substantive maintainer response. Findings are never silently deleted, because a silent delete would make every other appealed finding suspect. Every appeal gets a substantive public response that engages your specific argument.

A verified appeal triggers an **immediate re-scan**, and the team commits to publishing the updated score within **one hour** of acknowledging the verified appeal. The re-scan runs against the artifact at the exact commit SHA your appeal references (or current HEAD if none is supplied), and the response carries both the new score and the delta from the prior one. The appeal moves through documented states: `submitted` → `identity_verified` → `under_review` → `rescan_triggered` → `resolved_upheld` / `resolved_overturned` / `resolved_rule_changed`.

If you believe the rule itself is wrong — not just its application to your repo — that is the false-positive path, which fixes the rule for everyone rather than patching one score. See [Disputing findings](/docs/for-authors/disputing-findings/).

## What if I uploaded files instead of submitting a repo?

Directly uploaded artifacts have **no right-of-reply**. The right-of-reply is a vendor contract that presumes a discoverable upstream owner — a GitHub repo to verify against. An upload has no repo, no `.saferskills/verify.txt` path, no maintainer record, and no auto-rescan, so there is nothing to claim. What an upload does have:

- **Unlisted uploads** are reachable only through an unguessable share link. You can delete one yourself at any time with `DELETE /api/v1/scans/r/<token>`, and it auto-expires after 90 days.
- **Public uploads** can only be removed through the manual operator runbook — there is no automated takedown.

If you want a response channel, scan the public GitHub repo instead of uploading the files. See [Publish and get scanned](/docs/for-authors/publish-and-get-scanned/).

## Related

- [Disputing findings](/docs/for-authors/disputing-findings/) — challenge the rule, not just the score
- [Publish and get scanned](/docs/for-authors/publish-and-get-scanned/) — submit a repo so you can reply
- [Read a scan report](/docs/find-and-verify/read-a-scan-report/) — understand what a finding is claiming
