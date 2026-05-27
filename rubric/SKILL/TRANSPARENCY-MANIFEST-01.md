---
ruleId: SS-SKILL-TRANSPARENCY-MANIFEST-01
severity: medium
subScore: transparency
weight: 15
status: active
shadowUntil: null
appliesTo: [skill]
trigger:
  type: file_glob_absent
  paths: ['SKILL.md', '**/SKILL.md', 'skill.yaml', 'skill.yml', 'skill.json']
limitations:
  - "Fires only on the absence of the manifest file by canonical name; cannot detect a manifest stored under a non-canonical filename."
  - "Does not validate manifest contents — a present-but-empty SKILL.md satisfies the rule. Content-validation is a separate v2 rule under consideration."
priorArt:
  - https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills
  - https://github.com/anthropics/skills
---

# SS-SKILL-TRANSPARENCY-MANIFEST-01 — Missing skill manifest

## Rationale

A Claude Code skill is canonically defined by a `SKILL.md` (or analogous
`skill.yaml`/`.yml`/`.json`) manifest at the repo root or skill subdirectory.
The manifest declares the skill's purpose, expected inputs, and behavior
contract — it is what makes the skill discoverable and reviewable. A
repository tagged or registered as a skill but lacking any manifest is a
transparency failure: consumers cannot determine what the skill does without
reading every file in the repo.

The Anthropic skills catalog (`anthropics/skills`) treats SKILL.md as
required; the same convention applies across the MCP-skill ecosystem. We
detect by file-presence only — a present-but-empty manifest satisfies the
rule. Content quality (does the manifest describe what the skill does?) is
out of scope for v1 and may become a future rule.

Medium severity reflects the moderate impact: an undocumented skill is
harder to evaluate and audit, but does not in itself indicate hostile
behavior. The rule sits in the Transparency sub-score (weight 15%), where
file-presence checks are the dominant detection class. FP rate is
effectively zero (the rule's negative case is unambiguous).

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing — zero-FP file-presence check.
