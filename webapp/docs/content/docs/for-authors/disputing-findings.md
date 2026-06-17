---
title: "Disputing Findings"
description: "How to challenge a false positive: SaferSkills fixes the rule for everyone rather than quietly patching one score."
updated: 2026-06-16
---
If you believe a finding is a false positive, you dispute the **rule**, not your score. When a rule misfires, SaferSkills amends the rule itself — which corrects every artifact the rule scored, not just yours — rather than quietly editing one report. Findings are never silently deleted; they are annotated with the appeal outcome and kept in public history. The dispute runs through a verified, time-bounded appeal with a one-hour re-scan SLA.

## Why fix the rule instead of patching my score?

Because a false positive that hit your repo almost certainly hit others, and a per-score patch would leave them all wrong. A SaferSkills finding is reproducible from a documented rule trigger — there are no black-box findings — so if the trigger over-fires, the honest fix is to the trigger. When a verified appeal shows a rule misfired, the rubric is updated through the public rule-RFC process and the change applies corpus-wide. The original finding is annotated with the outcome and a clear "appealed and resolved" marker and stays in the public scan history; it is never silently removed. A silent delete would make every other appealed finding suspect, which is exactly the trust the audit trail exists to protect.

## How do I dispute a finding?

You submit a verified appeal, the same mechanism described in [Claim your repo](/docs/for-authors/claim-your-repo/). In short: prove ownership of the scanned repo (commit `.saferskills/verify.txt` with your GitHub username, or appeal from the maintainer email on record), then post your case at `/items/<slug>/respond`. Make the case concrete — name the `rule_id`, the file and line the finding cites, and why the rule's documented trigger does not actually apply to your code. The matched-line window the report shows you is the place to start; understanding exactly what the rule saw is covered in [Finding evidence](/docs/security-and-methodology/finding-evidence/).

Verification comes before any re-scan; an unverified appeal triggers nothing. A verified appeal triggers an **immediate re-scan**, and the maintainer team commits to publishing the updated score within **one hour** of acknowledging it. The re-scan runs against your artifact at the exact commit SHA the appeal references (or current HEAD), and its response carries the new score and the delta from the prior one.

## What are the possible outcomes?

An appeal moves through documented states and resolves one of three ways:

| State | What it means |
|---|---|
| `submitted` | Appeal received via form, issue, or email |
| `identity_verified` | Ownership confirmed by one of the two paths |
| `under_review` | A maintainer is assigned and investigating |
| `rescan_triggered` | The re-scan job is running (within 1h of verification) |
| `resolved_upheld` | The finding stands; a substantive public response is published next to it |
| `resolved_overturned` | The finding is overturned; the catalog is updated and the finding annotated |
| `resolved_rule_changed` | The rule itself was amended through the RFC workflow |

Every state transition is an audit event. Whatever the outcome, you get a **substantive public response** that engages your specific argument. Maintainers may not reject an appeal with "we already cover this," "the rule is correct" (without explaining why your argument fails on the rule's documented trigger), "you can't appeal this rule" (every rule is appealable), or "insufficient evidence" without naming what evidence would have sufficed.

## What if the rule is just missing or wrong by design?

If the issue is not a misfire on your repo but a gap or a design flaw in the rule corpus itself, the path is to propose the change directly. New rules and rule amendments go through a public rule-RFC with a comment window before a maintainer decision. See [Contribute a rule](/docs/security-and-methodology/contribute-a-rule/) for how to open one. When an appeal succeeds because the rule needed adjustment, it resolves as `resolved_rule_changed` and follows that same RFC process — your dispute and a rule contribution converge on the same governance.

## Where do I go next?

- [Claim your repo](/docs/for-authors/claim-your-repo/) — prove ownership and post your reply
- [Contribute a rule](/docs/security-and-methodology/contribute-a-rule/) — propose a new or amended rule
- [Finding evidence](/docs/security-and-methodology/finding-evidence/) — read exactly what a rule matched
