---
ruleId: SS-HOOKS-RCE-CHMOD-WIDE-01
severity: medium
subScore: security
weight: 15
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [hooks]
frameworks: ["owasp-llm:llm06", "mitre-atlas:AML.T0050", "cwe:732"]
title: >-
  Hook makes files world-writable
explanation: >-
  This hook runs automatically on an agent event. The spotted command <code>{match}</code>
  grants world-writable permissions (<code>777</code> / <code>a+rwx</code>) — breaking
  least-privilege and leaving the files open for any other process on the system to tamper with.
severityRationale: >-
  the resulting world-writable state lets any local process modify the affected files.
remediation:
  action: >-
    Grant only the permissions actually needed instead of full world-writable access.
  steps:
    - >-
      Replace <code>777</code> with the narrowest mode the task requires (e.g. <code>755</code> / <code>644</code>).
    - >-
      If cross-user access is genuinely needed, scope it with a group rather than world.
  saferPattern:
    before: |-
      chmod -R 777 ./shared
    after: |-
      chmod -R 755 ./shared
trigger:
  type: regex_match
  pattern: '(?i)\bchmod\s+(?:-R\s+)?(?:777|a\+rwx|o\+rwx|0?777)\b'
  scope:
    paths: ['.claude/hooks/**', 'hooks/**', '**/*.hook.sh', '**/SessionStart*', '**/PreToolUse*', '**/PostToolUse*']
limitations:
  - "Legitimate use: hooks that prepare a shared-temp-directory or socket for cross-user access. Shadow window measures FP rate."
  - "Cannot detect chmod 666 / 644 / other wide-but-not-fully-permissive patterns that still violate least-privilege."
  - "Cannot detect equivalent setfacl / takeown / icacls patterns on other platforms."
priorArt:
  - https://owasp.org/www-project-top-ten/2021/A05_2021-Security_Misconfiguration/
  - https://cwe.mitre.org/data/definitions/732.html
---

# SS-HOOKS-RCE-CHMOD-WIDE-01 — Hook grants world-writable permissions

## Rationale

A hook that runs `chmod 777` (or `chmod a+rwx`) widens file permissions to
world-writable, breaking least-privilege and creating a window for
post-install tampering. CWE-732 (Incorrect Permission Assignment) and
OWASP A05 (Security Misconfiguration) classify this as a baseline
hardening violation.

The medium severity reflects the secondary nature of the threat: the
hook itself isn't immediately destructive, but the post-chmod state is
exploitable by any other process on the system. Shadow because legitimate
use cases exist (creating cross-process IPC sockets, shared-cache
directories); the FP audit determines the operational threshold.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
