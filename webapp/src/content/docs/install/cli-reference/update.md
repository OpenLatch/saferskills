---
title: "saferskills update"
description: "Refresh installed capabilities to their latest scanned version and re-verify their trust scores."
updated: 2026-06-16
---
`saferskills update [--all]` refreshes installed capabilities and re-verifies their scores against the public catalog. Run it on a single capability by name, or with `--all` to refresh everything in your install registry. Because trust scores are recomputed on every re-scan, update is also how you discover that a capability you already trust has drifted — a new finding fired, or its supply-chain or maintenance signals changed since you installed it.

## How do I update a capability?

Update one capability by name, or all of them at once:

```bash
npx saferskills update mcp-server-github   # one capability
npx saferskills update --all               # every installed capability
```

For each capability, the CLI re-resolves it against the catalog, pulls its current scanned version, and re-verifies the [aggregate score](/docs/concepts/how-scoring-works/). If the capability has a newer scanned version than the one you have installed, update refreshes the agent config to match.

## Why does update re-verify the score?

Because a capability's score is not fixed. SaferSkills re-scans the public catalog continuously, and a score reflects whichever rules fired at the most recent scan — recorded against a `rubric_version` and a commit `ref_sha`. A maintainer can introduce a finding, transfer ownership, or let CI rot between the day you installed and today.

Re-verifying on update surfaces that drift. The same gate logic the [install](/docs/install/cli-reference/install/) command uses applies: a capability that has fallen below your `min_score`, or into the red Block band, is flagged so you can decide whether to keep it. SaferSkills reports the change and the rules behind it; it does not tell you to remove the capability — that decision is yours, informed by the [scan report](/docs/find-and-verify/read-a-scan-report/).

## What flags and exit codes apply?

| Flag | Effect |
|---|---|
| `--all` | Update every capability in the install registry, not just a named one. |
| `--json` | Emit machine-readable output on stdout. |
| `--yes` | Confirm without prompting. |
| `--non-interactive` (alias `--no-input`) | Never prompt. |

The full [global flags](/docs/install/global-flags/) apply. Exit codes follow the shared convention: `0` success, `1` a write failed and rolled back, `3` a named capability is not in the registry, `4` permission denied, `6` the API was unreachable or rate-limited.

## Where do I go next?

- [saferskills list](/docs/install/cli-reference/list/) shows current scores and drive age across your inventory.
- [saferskills install](/docs/install/cli-reference/install/) and [uninstall](/docs/install/cli-reference/uninstall/) manage what update tracks.
- [How scoring works](/docs/concepts/how-scoring-works/) explains the score that update re-verifies.
