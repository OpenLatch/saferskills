---
ruleId: SS-PLUGIN-SECRET-EXFIL-SSH-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [plugin]
trigger:
  type: regex_match
  pattern: '(?i)(~/.ssh/id_rsa|~/.ssh/id_ed25519|~/.ssh/id_ecdsa|/\.ssh/id_[a-z]+|BEGIN\s+(?:RSA|OPENSSH|DSA|EC)\s+PRIVATE\s+KEY)'
  scope:
    paths: ['**/*.py', '**/*.ts', '**/*.js', '**/*.mjs', '**/*.cjs', '**/*.go', '**/*.rb', '**/*.java']
limitations:
  - "Legitimate SSH-using plugins (git wrappers, SSH-key-rotation tools) reference the canonical paths."
  - "Cannot detect runtime-resolved key paths (e.g. paths read from config)."
  - "Cannot detect direct memory read of the SSH agent."
priorArt:
  - https://man.openbsd.org/ssh#FILES
  - https://snyk.io/blog/leaking-environment-variables-malicious-package/
  - https://attack.mitre.org/techniques/T1552/004/
---

# SS-PLUGIN-SECRET-EXFIL-SSH-01 — Plugin reads SSH private key files

## Rationale

A plugin that reads SSH private keys from the canonical filesystem
locations or embeds a private-key file format header (`BEGIN ... PRIVATE
KEY`) is engaging in either SSH-key-rotation tooling (rare in plugin
form) or credential exfiltration. MITRE ATT&CK T1552.004 (Private Keys)
catalogues the pattern.

High severity (not critical) reflects the secondary exposure path: SSH
keys are valuable but not always directly cloud-credentials-equivalent;
the impact depends on what the keys authorize. Active at landing — the
pattern set is canonical and FP risk is bounded.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
