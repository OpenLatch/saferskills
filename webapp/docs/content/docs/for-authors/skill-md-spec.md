---
title: "SKILL.md Spec"
description: "How to structure a skill bundle, its frontmatter, and the files that make it score well on a SaferSkills scan."
updated: 2026-06-16
author: "SaferSkills Team"
---
A skill is a directory anchored by a `SKILL.md` manifest that declares what the skill does, plus the documentation and licensing files a reviewer needs to trust it. SaferSkills scores a skill on five axes; this page describes the structure of a well-formed skill bundle, the manifest fields, and the concrete file-presence and content signals that move your [Transparency](/docs/security-and-methodology/5-sub-scores/) and [Security](/docs/concepts/glossary/#prompt-injection) sub-scores. Every signal below maps to a real, published rule.

## What is the shape of a skill bundle?

A skill is a directory, not a single file. The directory is recognized as a skill by the presence of a `SKILL.md` manifest at its root. SaferSkills' capability discovery walks a repository's file tree and treats any directory containing `SKILL.md` as a skill capability; one repository can hold several capabilities (a skill, an [MCP server](/docs/concepts/mcp-servers/), [hooks](/docs/concepts/hooks/)), and each is discovered and scored independently. A minimal, scannable bundle looks like this:

```text
my-skill/
├── SKILL.md          # the manifest — what makes this a skill
├── README.md         # human entry point: what it does, how to use it
├── LICENSE           # how the artifact may be used
├── CHANGELOG.md      # what changed between releases
├── SECURITY.md       # how to report a vulnerability
└── scripts/          # any supporting code, kept out of the docs
```

None of these files is invented for SaferSkills. `SKILL.md` is the canonical Claude Code skill manifest ([Anthropic skills documentation](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills)); the surrounding files are standard open-source hygiene. SaferSkills scores their presence because each one is a transparency signal a reviewer relies on before letting an agent load your skill.

## What goes in the SKILL.md manifest?

`SKILL.md` is Markdown with a YAML frontmatter block. The frontmatter declares the skill's identity; the body explains its behavior. At minimum, declare a `name` and a `description`:

```markdown
---
name: pdf-extract
description: Extracts text from PDF files in the working directory.
---

# pdf-extract

This skill reads PDF files in the current working directory and returns their
text content. It does not write files, make network calls, or run shell
commands.
```

The `description` is the field an agent reads to decide whether the skill is relevant to a task, so make it a precise statement of purpose, expected inputs, and behavior — the contract a reviewer can check the skill against. SaferSkills detects the manifest by filename (it accepts `SKILL.md`, `skill.yaml`, `skill.yml`, or `skill.json`), and at v1 it checks for *presence*, not content quality: a present-but-empty manifest satisfies the structural rule. Even so, an empty manifest defeats the purpose — the reason the manifest counts is that it lets a reviewer evaluate your skill without reading every file in the repo.

## What makes a skill score well?

A skill scores well on two independent fronts: it is **transparent** (the documentation a reviewer needs is present) and it is **clean** (the source contains none of the injection or obfuscation patterns that trip the Security sub-score). The two are scored separately and both matter.

### The transparency files

The [Transparency sub-score](/docs/security-and-methodology/5-sub-scores/) is dominated by file-presence checks. Each missing file is a documented finding; the cumulative effect of missing several is a meaningful sub-score reduction, while adding each is a one-time, low-cost fix. The signals, with their real rules:

- **A skill manifest** — missing `SKILL.md` fires `SS-SKILL-TRANSPARENCY-MANIFEST-01` (medium). An undocumented skill cannot be evaluated before an agent runs it.
- **A LICENSE file** — missing it fires `SS-SKILL-TRANSPARENCY-LICENSE-01` (medium). Without a license the artifact is "all rights reserved" by default, which leaves consumers with no clear right to redistribute, modify, or install it. Commit an OSI-approved license as `LICENSE` at the repo root (the rule accepts `LICENSE.md`, `LICENSE.txt`, `COPYING`, and the `LICENCE` spellings).
- **A README** — missing it fires `SS-SKILL-TRANSPARENCY-DESCRIPTION-01` (low). The README is the canonical entry point that states what the artifact does, so a reviewer is not forced to read source or run it speculatively. The rule checks `README.md`, `README`, `README.rst`, `README.txt`.
- **A CHANGELOG** — missing it fires `SS-SKILL-TRANSPARENCY-CHANGELOG-01` (low). Without a record of what changed between releases, an installer cannot tell a benign patch from a behavior- or license-changing update without reading the diff. The [Keep a Changelog](https://keepachangelog.com/) format is the convention; the rule accepts `CHANGELOG.md`, `CHANGELOG`, `CHANGELOG.txt`, `CHANGES.md`, `HISTORY.md`.
- **A SECURITY.md disclosure policy** — missing it fires `SS-SKILL-TRANSPARENCY-SECURITY-01` (low). For code that runs in privileged agent contexts, a stated way to report a vulnerability is the operational baseline for responsible disclosure. The rule checks the repo root, `.github/`, and `docs/`.

:::tip
These five files are the cheapest points on the board. They are file-presence checks with effectively zero false-positive rate, so adding `SKILL.md`, `LICENSE`, `README.md`, `CHANGELOG.md`, and `SECURITY.md` reliably lifts the Transparency sub-score with one PR.
:::

A note on what these rules do *not* check: at v1 they assess presence, not content. A LICENSE containing arbitrary text, a one-line README, or an empty CHANGELOG all satisfy the structural rule. Content validation (SPDX-identifier checks, manifest-content quality) is a deferred enhancement, not a present-tense claim. Documentation managed entirely outside the repo — a GitHub-Releases-only changelog, a GHSA-only disclosure policy with no file — is not detected and still fires the rule, so commit the file even if you also publish elsewhere.

### Keeping the source clean

The [Security sub-score](/docs/security-and-methodology/5-sub-scores/) carries 35% of the aggregate weight, and a single serious finding caps the whole score regardless of how good your docs are (an active critical caps the aggregate at ≤15; an active high at ≤45). The patterns that fire here are the ones that turn skill *documentation* into an executable payload, because an agent reads your `SKILL.md` as trusted instructions. The most consequential, with their real rules:

- **No invisible Unicode** — Plane-14 "tag" characters (U+E0000–U+E007F) render as nothing to a human but tokenize for every LLM, letting an attacker hide a whole second instruction. `SS-SKILL-INJECT-UNICODE-TAG-01` (critical) fires on any presence; there is no legitimate authoring use for these codepoints. If you ever paste from an untrusted source, run a strip-and-diff: remove all plane-14 characters and confirm the visible text is unchanged.
- **No fenced "run this" imperatives** — a fenced `bash`/`python` block that carries a natural-language imperative ("now run this", "execute the following") directs the agent to execute the fence. `SS-SKILL-INJECT-FENCED-RUN-01` (high) catches this. If you must show setup, label the block `text` rather than `bash` so it reads as prose, and move any real installer into a reviewed, version-pinned script you link to.
- **No long encoded blobs** — a base64 string of 128+ characters in a documentation file is the encoded-injection pattern: the hostile instruction is hidden from keyword filters but trivially decoded by the agent at runtime. `SS-SKILL-INJECT-B64-PAYLOAD-01` (high) fires on it. There is no normal reason to embed a multi-hundred-byte base64 blob in skill docs — keep signatures and binary data in dedicated files (`*.sig`, `SIGNATURES`) outside the documentation.

These are three of the security rules that apply to skills; SaferSkills also checks for [prompt injection](/docs/concepts/glossary/#prompt-injection) via imperative phrasing, role-play overrides, homoglyphs, bidirectional-text tricks, and zero-width characters. Browse the full, current list — every rule with its severity, trigger, and limitations — on the [live methodology page](/methodology).

## How do I confirm my changes worked?

Re-submit the repo at [/scan](/scan) and read the updated report. Because scoring is deterministic, the same bytes against the same `rubric_version` always produce the same score, so you can iterate locally and verify each change lands. The report renders the per-finding penalty and the running sub-score, so you can see exactly which file or pattern moved the number. To install your scanner-clean skill into an agent, or to gate installs on a minimum score, see [Install a skill](/docs/install/install-a-skill/).

## Related

- [Publish and get scanned](/docs/for-authors/publish-and-get-scanned/) — submit your repo
- [How scoring works](/docs/security-and-methodology/how-scoring-works/) — the deterministic model behind these signals
- [Detection categories](/docs/security-and-methodology/detection-categories/) — the closed set of rule categories
- [The live methodology page](/methodology) — the full, current rule list

**Author:** SaferSkills Team — methodology maintainers.
