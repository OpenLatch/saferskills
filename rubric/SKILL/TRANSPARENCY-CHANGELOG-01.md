---
ruleId: SS-SKILL-TRANSPARENCY-CHANGELOG-01
severity: low
subScore: transparency
weight: 8
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: file_glob_absent
  paths: ['CHANGELOG.md', 'CHANGELOG', 'CHANGELOG.txt', 'CHANGES.md', 'HISTORY.md']
limitations:
  - "Does not validate the changelog content or format (Keep a Changelog, conventional commits, etc.). Presence is the only check."
  - "GitHub-Release-managed changelogs (release notes per tag) are not detected — the rule fires even when the maintainer uses release notes instead of a file. v2 may consult the GitHub Releases API."
priorArt:
  - https://keepachangelog.com/
  - https://semver.org/
---

# SS-SKILL-TRANSPARENCY-CHANGELOG-01 — Missing CHANGELOG file

## Rationale

A CHANGELOG (in any of the canonical filenames) signals that the maintainer
documents what changed between releases. Without it, consumers cannot
distinguish a benign patch release from a behavior-changing or
license-changing one — they must read the diff themselves. The Keep a
Changelog convention (keepachangelog.com) codifies the canonical format; many
ecosystems (npm, PyPI) auto-link to CHANGELOG.md on the package detail page.

The rule fires on absence of any canonical changelog filename. A
GitHub-Releases-only changelog (no file in the repo) is not detected by v1 —
this is a known limitation and a v2 enhancement candidate that requires a
GitHub API call. The low severity reflects the modest impact: missing a
changelog is a transparency reduction, not a security exposure, and many
small or single-purpose tools legitimately do without one.

Low severity, weight 8: meaningful enough to register on the Transparency
sub-score (15% aggregate weight) but not severe enough to materially affect
the tier band. Active at landing — zero-FP file-presence check.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
