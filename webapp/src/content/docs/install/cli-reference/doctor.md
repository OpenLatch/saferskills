---
title: "saferskills doctor"
description: "Diagnose registry-vs-filesystem drift across detected agents; --fix re-applies drifted install records."
updated: 2026-06-16
---
`saferskills doctor` diagnoses drift between the SaferSkills install registry and what is actually on disk across your detected agents. It compares each record in `~/.saferskills/installs.json` against the corresponding agent config file and reports where they disagree — an install the registry expects but the filesystem no longer has, or an entry edited out of band. Adding `--fix` re-applies the drifted records so the filesystem matches the registry again.

## How do I run doctor?

Run it with no arguments to get a read-only diagnosis:

```bash
npx saferskills doctor
```

For each detected agent, doctor walks the install registry and checks that every recorded capability is still present and correct in that agent's config. It reports the agents it found, the records it checked, and any drift — without writing anything.

## What does --fix do?

`--fix` re-applies the drifted install records, restoring agent config to match the registry:

```bash
npx saferskills doctor --fix
```

This is the repair path: where doctor found a registry record whose on-disk config had drifted, `--fix` re-writes the agent config from the registry. It re-applies records — it does not invent new ones or remove capabilities you added by hand outside the CLI. As with [install](/docs/install/cli-reference/install/) and [uninstall](/docs/install/cli-reference/uninstall/), a config write that fails mid-flight is rolled back, so a failed repair never leaves an agent half-edited.

## When should I run it?

Run doctor when an installed capability seems missing or behaves unexpectedly, after editing an agent's config by hand, or after moving machines. It diagnoses **registry-versus-filesystem** drift specifically — to check whether an installed capability's *score* has drifted (a new finding fired since you installed), use [`update`](/docs/install/cli-reference/update/), which re-verifies trust scores instead.

## What flags and exit codes apply?

The [global flags](/docs/install/global-flags/) apply — `--json` for machine-readable diagnosis on stdout, `--yes` to confirm repairs non-interactively, `--quiet`/`--verbose`. Exit codes follow the shared convention: `0` when nothing is wrong (or `--fix` repaired everything), `1` when drift remains or a repair write failed, `4` on a permission error reading or writing agent config.

## Where do I go next?

- [saferskills list](/docs/install/cli-reference/list/) shows your inventory and per-capability scores.
- [saferskills update](/docs/install/cli-reference/update/) re-verifies scores, the complement to doctor's filesystem check.
- [Managing your agents](/docs/concepts/managing-your-agents/) explains how the CLI tracks installs across agents.
