---
ruleId: SS-HOOKS-RCE-SUDO-UNATTENDED-01
severity: high
subScore: security
weight: 25
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [hooks]
trigger:
  type: regex_match
  pattern: '(?i)\bsudo\s+(?:-[ASEnk]+\s+)?\b|\becho\s+["'']?\$[A-Z_]+["'']?\s*\|\s*sudo\s+-S\b|\bNOPASSWD\b'
  scope:
    paths: ['.claude/hooks/**', 'hooks/**', '**/*.hook.sh', '**/SessionStart*', '**/PreToolUse*']
limitations:
  - "Legitimate use case: installation hooks for tools that genuinely require root (rare in agent-tool ecosystems). Shadow window measures real-world FP."
  - "Cannot distinguish a sudo invocation that would prompt the user (acceptable) from a sudo invocation backed by NOPASSWD or a piped-password (unacceptable)."
  - "Does not cover Windows runas / elevation equivalents — v2 extension."
priorArt:
  - https://owasp.org/www-community/attacks/Command_Injection
  - https://snyk.io/blog/post-install-scripts-supply-chain-attacks/
---

# SS-HOOKS-RCE-SUDO-UNATTENDED-01 — Unattended privilege escalation in hook

## Rationale

A hook that invokes `sudo` — especially with `-S` (read password from
stdin), `-n` (non-interactive, fail if password needed), or in a system
configured with NOPASSWD — is performing privilege escalation without a
user-confirmation gate. The Snyk supply-chain analysis documents this
pattern as one of the highest-impact post-install attack vectors:
package authors who add unattended sudo to install hooks have a clean
escalation path to root on any consumer's machine.

The FP risk is real: some legitimate tools (installers for system-level
services, kernel modules, etc.) genuinely need root. The shadow window
will quantify how often hooks fire sudo legitimately vs adversarially.
The most likely promotion path is to narrow the trigger to require both
sudo and one of the unattended-flag indicators (`-S`, `-n`, NOPASSWD); a
plain interactive `sudo apt install` may not warrant the high-severity
treatment if the user is genuinely prompted.

High severity reflects the impact class. Shadow until the FP audit
quantifies the trade-off.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
