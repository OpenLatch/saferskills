---
ruleId: SS-HOOKS-OBFUSCATION-B64-SHELL-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [hooks]
trigger:
  type: regex_match
  pattern: '(?i)\b(?:echo|printf)\s+["'']?[A-Za-z0-9+/=]{32,}["'']?\s*\|\s*(?:base64\s+(?:-d|--decode)|openssl\s+base64\s+-d)\s*\|\s*(?:bash|sh|zsh)\b|\bbase64\s+(?:-d|--decode)\s+<<<\s*["''][A-Za-z0-9+/=]{32,}["'']\s*\|\s*(?:bash|sh)\b'
  scope:
    paths: ['.claude/hooks/**', 'hooks/**', '**/*.hook.sh', '**/SessionStart*', '**/PreToolUse*', '**/PostToolUse*']
limitations:
  - "Cannot detect base64-shell pipelines that split the encoded payload across variables before piping."
  - "Cannot detect hex-encoded or otherwise-encoded shell payloads (those would be a separate rule)."
  - "Cannot detect base64-decode chains that route through a temp file before execution."
priorArt:
  - https://owasp.org/www-community/attacks/Command_Injection
  - https://attack.mitre.org/techniques/T1027/
  - https://snyk.io/blog/post-install-scripts-supply-chain-attacks/
---

# SS-HOOKS-OBFUSCATION-B64-SHELL-01 — Base64-decoded shell execution in hook

## Rationale

The base64-decode-and-pipe-to-shell pattern (`echo "..." | base64 -d | bash`)
is the canonical obfuscation technique for hiding adversarial shell from a
human reviewer. MITRE ATT&CK T1027 (Obfuscated Files or Information)
catalogues it as a baseline malware technique; Snyk's supply-chain analysis
documents its use in post-install scripts.

A hook that contains this pattern is almost certainly adversarial: the
encoding step has no legitimate purpose in a hook (which is itself plain
text the user can read). The encoding exists specifically to evade review.
High severity is appropriate.

Active at landing because the FP profile is well-bounded: the regex
requires the full decode-and-pipe-to-shell pipeline; merely having a
base64 string in a hook (a config token, an embedded image) does not
trigger.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
