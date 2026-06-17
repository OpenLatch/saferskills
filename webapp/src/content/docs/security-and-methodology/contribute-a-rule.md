---
title: "Contribute a Rule"
description: "Propose a detection rule via an RFC, write the rule YAML, and follow it through shadow-to-active review."
updated: 2026-06-16
author: "SaferSkills Team"
---
Contributing a detection rule starts with a public RFC, not a pull request. You open a rule-proposal issue, the maintainers run a comment window and decide, and only then does a PR add the rule's Markdown-plus-YAML file under `rubric/`. Every rule is Apache-2.0, publicly documented, and lands in a shadow state — firing at weight 0 — until a false-positive audit promotes it to active. Closed-source rules are never accepted.

## Why does a rule start with an RFC?

Because SaferSkills' credibility rests on a public, auditable rubric, every rule is proposed in the open before any code lands. The workflow is:

1. **Open an RFC issue** using the [`03-rule-proposal.yml`](https://github.com/OpenLatch/saferskills/blob/main/.github/ISSUE_TEMPLATE/03-rule-proposal.yml) template, titled `RFC: SS-<CATEGORY>-<NAME>-NN — <short description>`. The RFC must include the proposed `title`, `explanation`, and `remediation` so reviewers can judge the finding a user would actually see.
2. **A 7-day comment window** opens, labeled `rfc/discussion`. Anyone can comment.
3. **A maintainer decides** at the end of the window: `rfc/accepted` proceeds to a PR; `rfc/rejected` closes with a substantive written rationale; `rfc/needs-changes` extends the window once.
4. **An implementation PR** adds `rubric/<CATEGORY>/<NAME>-NN.md` plus its trigger config and tests, and links the RFC issue.

Do not skip the RFC and open a rule PR directly — it will be asked to start with the proposal. The RFC is where the rule's value, its false-positive risk, and its severity are debated in public.

## Where does the rule file live and what is its ID?

Rules live at `rubric/<CATEGORY>/<NAME>-NN.md`, one Markdown file with YAML frontmatter per rule. The `rule_id` follows the grammar `SS-<CATEGORY>-<NAME>-NN`:

- `SS-` is the fixed prefix.
- `<CATEGORY>` is one of the closed set `MCP`, `SKILL`, `RULES`, `HOOKS`, `PLUGIN`.
- `<NAME>` is uppercase kebab-case (for example `INJECT-FENCED-RUN`, `RCE-CURL-PIPE`).
- `NN` is a two-digit zero-padded sequence.

The ID is validated against the regex `^SS-(MCP|SKILL|RULES|HOOKS|PLUGIN)-[A-Z][A-Z0-9-]*-\d{2}$`. Real examples in the rubric today include `SS-SKILL-INJECT-FENCED-RUN-01`, `SS-MCP-POISON-UNICODE-TAG-01`, and `SS-HOOKS-RCE-CURL-PIPE-01`. See [detection categories](/docs/security-and-methodology/detection-categories/) for how categories and rule families relate.

## What does the rule YAML require?

Every rule's frontmatter is validated against [`schemas/rubric-rule.schema.json`](https://github.com/OpenLatch/saferskills/blob/main/schemas/rubric-rule.schema.json); a rule missing a required field fails the `validate` CI lane. The required fields:

| Field | Content |
|---|---|
| `ruleId` | `SS-<CATEGORY>-<NAME>-NN`. |
| `severity` | `info` / `low` / `medium` / `high` / `critical`. |
| `subScore` | `security` / `supply_chain` / `maintenance` / `transparency` / `community`. |
| `weight` | Integer 0–40 — the maximum penalty this rule contributes. |
| `status` | `shadow` / `active` / `deprecated`. New rules land `shadow`. |
| `appliesTo` | A non-empty subset of `[skill, mcp, rules, hooks, plugin]`. |
| `trigger` | One of the six trigger primitives (below). |
| `title` | Plain-English headline, no rule_id. |
| `explanation` | One or two second-person sentences: the risk and outcome class. |
| `remediation` | An object with a required `action`, optional `steps`, and an optional `saferPattern { before, after }`. |
| `limitations` | A non-empty list naming what the rule cannot catch — **mandatory**. |
| `priorArt` | URLs to CVEs, OWASP entries, papers, or write-ups that motivate the rule. |

Optional fields include `severityRationale` (omit for `info`-tier), `categoryLabel`, `shadowUntil` (required when `status` is `shadow`), and `frameworks` — short taxonomy codes (`owasp-llm:<id>`, `mitre-atlas:<id>`, `cwe:<id>`) that resolve into clickable badges. An unknown framework code hard-fails the generator, and the `saferPattern` `after` snippet must always be a pattern, never a product, in keeping with the rubric's anti-recommendation stance.

## What are the six trigger types?

The trigger is the detection logic, and it must be one of a closed set of six primitives — adding a new primitive itself requires an RFC:

- `regex_match` — a pattern over scoped file paths.
- `file_glob_present` — a file matching a glob exists.
- `file_glob_absent` — a file matching a glob is missing (the LICENSE/SECURITY.md checks).
- `commit_history_check` — a repository-history signal (commit age, frequency, issue-response time) compared against a threshold.
- `metadata_check` — a repository-metadata field (stars, forks, license, owner age) compared against a value.
- `composite_and_or` — a boolean combination of the above.

Because the trigger is a documented primitive rather than a model call, the resulting finding is deterministic and reproducible — the foundation described in [finding evidence](/docs/security-and-methodology/finding-evidence/).

## How is severity decided and reviewed?

Severity is proposed in the RFC and reviewed by a maintainer, because it directly controls a rule's impact: an `info` rule carries weight 0, while a `critical` rule contributes a 40-point penalty and can trigger the aggregate severity ceiling. The severity must be justified by the outcome class — `SS-SKILL-INJECT-FENCED-RUN-01` is `high` because a successful injection runs attacker-supplied shell — and the optional `severityRationale` field captures that justification on the finding card. See [how scoring works](/docs/security-and-methodology/how-scoring-works/) for how severity maps to penalties and bands.

## What happens after the rule is merged?

Every new rule lands in `status: shadow`, regardless of how confident the author is. During the shadow window the detector fires and records findings in the public scan trace, but the rule's weight is 0 — it has no score impact. After 7 days a false-positive audit harness gates promotion: a false-positive rate under 10% on the hand-labelled fixture promotes the rule to `status: active`; a rate of 10% or higher extends the shadow window with maintainer review. This protects against launch-week false positives without delaying the detection signal.

Rules are never silently retired, either. Deprecation goes through its own RFC, a one-minor-version wind-down with a "deprecation pending" annotation, and finally code removal — but the rule doc stays in git history forever, because historical scans must remain explainable.

## What license applies to a contributed rule?

SaferSkills is [Apache-2.0](https://github.com/OpenLatch/saferskills/blob/main/LICENSE), and so is every rule you contribute. The rubric is public by design — closed-source rules do not ship, because a detection SaferSkills cannot describe in a `rubric/<CATEGORY>/<NAME>-NN.md` file cannot be audited or reproduced by the vendors it scores. Start your contribution from the [SaferSkills repository](https://github.com/OpenLatch/saferskills) and the rule-proposal template, and read [finding evidence](/docs/security-and-methodology/finding-evidence/) to understand exactly what a user will see when your rule fires.

**Author:** SaferSkills Team — methodology maintainers.
