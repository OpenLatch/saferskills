---
ruleId: SS-SKILL-TRANSPARENCY-LICENSE-01
severity: medium
subScore: transparency
weight: 15
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: file_glob_absent
  paths: ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING', 'COPYING.md', 'LICENCE', 'LICENCE.md']
limitations:
  - "Does not validate license content — a LICENSE file containing arbitrary text satisfies the rule. License-validity is enforced via a separate SPDX-identifier check (deferred)."
  - "Cannot detect license declarations embedded only in package.json / pyproject.toml without a separate LICENSE file. The W2 v1 rule treats the file's presence as the canonical declaration."
priorArt:
  - https://choosealicense.com/no-permission/
  - https://opensource.org/osd
  - https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository
---

# SS-SKILL-TRANSPARENCY-LICENSE-01 — Missing LICENSE file

## Rationale

A repository without a LICENSE file is by default not open-source under U.S.
copyright law — all rights reserved to the author. For artifacts that
distribute themselves as installable skills, MCP servers, hooks, plugins, or
rule files, the absence of a license creates legal ambiguity for consumers
and prevents redistribution, modification, or sometimes even local
installation depending on the consumer's compliance posture. GitHub's own
documentation flags unlicensed repositories as a usage risk; the choosealicense.com
project (maintained by GitHub) provides the canonical guidance.

The detection is a strict file-glob-absent check across the canonical license
filename variants. A present LICENSE file satisfies the rule regardless of
content; SPDX-identifier validity is a deferred v2 enhancement that requires
parsing the license text against the SPDX catalog.

Medium severity is justified because the impact is consumer-facing legal risk
(not direct security exposure) but the cost to the maintainer of adding a
LICENSE is trivial (a one-time PR). The rule sits at the Transparency layer:
a maintained, well-documented skill ships its license.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing — zero-FP file-presence check.
