---
ruleId: SS-SKILL-INJECT-B64-PAYLOAD-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [skill, mcp, rules, hooks, plugin]
trigger:
  type: regex_match
  pattern: '(?<![A-Za-z0-9+/=])(?:[A-Za-z0-9+/]{4}){32,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?(?![A-Za-z0-9+/=])'
  scope:
    paths: ['**/*.md', '**/*.yaml', '**/*.yml', '**/*.json', '**/SKILL.md', '**/CLAUDE.md']
limitations:
  - "Cannot distinguish injection payloads from legitimate base64 (e.g. embedded test fixtures, SHA hashes presented in base64, signed manifests). Operates on the *presence* of a sufficiently long base64-shaped string in a documentation file as a signal."
  - "Does not decode the payload at scan time — the engine flags the pattern; review by maintainer or vendor surfaces the decoded content."
  - "Requires ≥128 base64 chars (32 quartets) to fire. Shorter strings (typical signatures / hashes) do not trigger."
priorArt:
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/
  - https://embracethered.com/blog/posts/2024/encoded-prompt-injections/
  - https://arxiv.org/abs/2310.02446
---

# SS-SKILL-INJECT-B64-PAYLOAD-01 — Base64-encoded payload in skill source

## Rationale

Encoded prompt injection (Embrace the Red, 2024; arXiv 2310.02446) embeds the
hostile instruction in base64, hex, or other reversible encoding inside a
skill body, then includes a separate plain-text instruction asking the
consuming model to decode and act on the encoded content. The pattern defeats
keyword-based detection (the visible text doesn't contain "ignore previous
instructions" or any other tripwire phrase) while remaining trivially
recoverable by the consuming LLM, which is highly capable of base64 decoding.

The rule fires on any sufficiently long base64-shaped string (≥128 chars,
which is 96 bytes decoded — too short for typical signatures, long enough for a
meaningful injection payload) in a documentation file. There is no legitimate
authoring reason to embed a multi-hundred-byte base64 string in skill
documentation; signed manifests live in dedicated files (`SIGNATURES`,
`*.sig`) outside the scope.

`high` severity is appropriate: the encoded-payload pattern is a high-skill
attack (the author understood and deliberately constructed it), the decode
step is reliable, and the resulting injection has the same impact class as
plain-text injection. Active at landing because the FP profile is well-bounded
(the 128-char threshold and exclusion of source-code extensions where base64
constants are common — `.py`/`.ts`/`.js`/`.sh` not in scope — suppresses the
common FP modes).

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
