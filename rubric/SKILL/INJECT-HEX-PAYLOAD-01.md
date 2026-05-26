---
ruleId: SS-SKILL-INJECT-HEX-PAYLOAD-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: regex_match
  pattern: '(?i)(?<![0-9a-f])([0-9a-f]{256,})(?![0-9a-f])'
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/SKILL.md', '**/CLAUDE.md']
limitations:
  - "Cannot distinguish hex-encoded injection payloads from legitimate hex constants (SHA-256 of a known artifact, signed manifest entries). Operates on the *presence* of a sufficiently long hex-shaped string in documentation as a signal."
  - "Requires ≥256 hex chars (128 bytes decoded) to fire — well above typical SHA-256 (64 hex chars) so single-hash inclusions do not trigger."
  - "Does not decode the payload at scan time."
priorArt:
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://embracethered.com/blog/posts/2024/encoded-prompt-injections/
---

# SS-SKILL-INJECT-HEX-PAYLOAD-01 — Hex-encoded payload in skill source

## Rationale

Hex-encoding is the parallel encoding to base64 (covered in
SS-SKILL-INJECT-B64-PAYLOAD-01) for the same attack pattern: hide the
adversarial instruction in a reversible encoding the model can decode at
runtime, defeating keyword-based detection. Encoded prompt injection
(Embrace the Red, 2024) is documented to work reliably across major LLMs;
the OWASP LLM Top 10 2025 LLM01 classifies the broader encoded-payload
class as a direct-injection vector.

The threshold of ≥256 hex characters (128 decoded bytes) is well above
typical SHA-256 hashes (64 chars) and signature constants — these would
generate too many false positives. The lower bound is also well above the
shortest meaningful injection payload, which our research suggests starts
around 80 bytes / 160 hex chars; the 256-char floor preserves both ends.

The rule is scoped to documentation file types (`.md` / `.yaml` / `.yml` /
`SKILL.md` / `CLAUDE.md`) and explicitly excludes source-code files where
hex constants are routine (cryptographic test fixtures, embedded firmware
addresses, color tables). This scoping is critical to FP control.

`high` severity matches the base64 sibling rule. Active at landing under the
same FP-confidence justification: the threshold is empirically chosen to
suppress incidental FP while catching the deliberate-payload pattern, and the
post-shadow promotion of the base64 sibling provides direct precedent.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
