---
ruleId: SS-SKILL-INJECT-BIDI-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
frameworks: ["owasp-llm:llm01", "mitre-atlas:AML.T0051"]
title: >-
  Bidirectional-override characters that make the text read differently than the agent sees it
categoryLabel: >-
  Obfuscation
explanation: >-
  A Right-to-Left Override or isolate character (U+202A–U+202E, U+2066–U+2069) reorders
  how the line displays without changing what the tokenizer reads — the Trojan Source
  trick. The file can look harmless to you while injecting hostile instructions at the
  token level, and the deception survives copy-paste into a sandbox.
severityRationale: >-
  the displayed text diverges entirely from the tokenized content, defeating any review-by-reading.
remediation:
  action: >-
    Remove the bidi-override characters and retype the affected line in plain left-to-right ASCII.
  steps:
    - >-
      Delete every U+202A–U+202E and U+2066–U+2069 character from the file.
    - >-
      If you genuinely need mixed-script text, rely on script-aware rendering and document the need in a SKILL.md <code># i18n</code> section.
trigger:
  type: regex_match
  pattern: '[\u{202A}-\u{202E}\u{2066}-\u{2069}]'
  flags: u
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/*.json', '**/SKILL.md', '**/*.py', '**/*.ts', '**/*.js', '**/*.sh']
limitations:
  - "Cannot detect BiDi attacks that use RTL-marker-free scripts (Arabic / Hebrew script blocks have inherent RTL); rule scopes to explicit BiDi-override codepoints only."
  - "Cannot distinguish legitimate i18n use (mixed-script documentation) from injection — fires on any explicit override character. Reviewers should examine context."
priorArt:
  - https://www.trojansource.codes/
  - https://nvd.nist.gov/vuln/detail/CVE-2021-42574
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
---

# SS-SKILL-INJECT-BIDI-01 — BiDi override prompt injection

## Rationale

The Trojan Source attack (Boucher & Anderson, University of Cambridge, 2021;
CVE-2021-42574) exploits Unicode's bidirectional algorithm to make source files
display differently from how a compiler — or an LLM tokenizer — actually
interprets them. By inserting Right-to-Left Override (U+202E), Left-to-Right
Override (U+202D), or the four Isolate variants (U+2066–U+2069), an attacker can
make a skill body or MCP tool description read benignly to a human reviewer
while injecting hostile instructions at the token level. Every major compiler
toolchain shipped a CVE response in 2021; LLM agent platforms have not, and the
2025 OWASP LLM Top 10 LLM01 explicitly lists BiDi smuggling as an indirect-
injection vector.

`critical` severity is appropriate because: (1) the visual presentation of the
file completely diverges from its tokenized content, defeating any review-by-
reading workflow including the SaferSkills maintainer audit itself; (2) the
override is durable across copy-paste — a reviewer who copies the apparent text
into a sandboxed evaluation will not reproduce the actual LLM input; and (3) the
defensive cost of stripping these codepoints from skill source is zero, so we
hold authors to a strict standard. The rule's scope extends to source code
(`.py`/`.ts`/`.js`/`.sh`) as well as text artifacts because hooks may be
arbitrary scripts that the LLM agent will read for behavior context.

Legitimate i18n use of explicit BiDi-override codepoints in skill source is rare
(modern systems use script-aware rendering without overrides). When a vendor
appeals citing real i18n need, the appeal path documents the legitimate use in
the SKILL.md `# i18n` section; the rule then gains a documented exception.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Active at landing.
