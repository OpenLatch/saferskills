---
ruleId: SS-HOOKS-RCE-RMRF-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [hooks]
frameworks: ["owasp-llm:llm06", "mitre-atlas:AML.T0050", "cwe:78"]
title: >-
  Hook recursively force-deletes a risky path
categoryLabel: >-
  Command execution
explanation: >-
  This hook runs automatically on an agent event, with no chance for you to stop it.
  The spotted command <code>{match}</code> recursively force-deletes a root, home, or
  variable-expanded path — if the path resolves wrong at runtime, it irreversibly destroys data.
severityRationale: >-
  the hook can irreversibly destroy user or system data automatically, with no confirmation gate.
remediation:
  action: >-
    Remove the recursive force-delete, or scope it to a fixed relative directory you control.
  steps:
    - >-
      Never <code>rm -rf</code> against <code>/</code>, <code>~</code>, or an unexpanded variable.
    - >-
      Target an explicit relative path and guard it so an empty variable can't widen the delete.
  saferPattern:
    before: |-
      rm -rf "$BUILD_DIR"
    after: |-
      BUILD_DIR="${BUILD_DIR:?build dir unset}"
      rm -rf "./build/${BUILD_DIR##*/}"
trigger:
  type: regex_match
  pattern: '(?i)\brm\s+(?:-[rRfF]+\s+|--recursive\s+|--force\s+)+(?:/(?:\s|$|\*|[a-zA-Z][a-zA-Z0-9/_-]*)|\$\w+|~/?\s*$|"\$\{?\w+\}?")'
  scope:
    paths: ['.claude/hooks/**', 'hooks/**', '**/*.hook.sh', '**/*.hook.ps1', '**/SessionStart*', '**/SessionEnd*', '**/PreToolUse*', '**/PostToolUse*']
limitations:
  - "Cannot detect `rm -rf` with paths constructed via complex variable expansion (the rule catches `$VAR` directly but not `\"${BASE}/${SUBDIR}\"` chains)."
  - "Cannot detect PowerShell `Remove-Item -Recurse -Force` equivalents — that pattern is a v2 extension."
  - "Cannot distinguish a `rm -rf` that legitimately cleans a known temp directory from one that destroys user data; the rule treats hook-scope `rm -rf` as universally suspicious."
priorArt:
  - https://owasp.org/www-community/attacks/Command_Injection
  - https://www.bleepingcomputer.com/news/security/steam-game-mod-breaks-other-mods-deletes-system-files/
---

# SS-HOOKS-RCE-RMRF-01 — `rm -rf` with risky path in hook

## Rationale

A `rm -rf` invocation in a Claude Code hook, especially one targeting `/`,
`$VARIABLE`, `~`, or any user-controlled path, is the canonical destructive
RCE pattern. The 2024 Steam mod incident (Bleeping Computer) is a recent
example of the class: a hook-like installer that ran `rm -rf` against
incorrectly-parsed paths and destroyed user data. In a hook running with
the user's privileges, this is unbounded data loss.

The trigger matches the dangerous-path subset: rm with -rf (or
--recursive/--force) targeting `/` (root deletion candidate), a variable
(unknown expansion at runtime), or a home-directory expansion. The
common-safe case (`rm -rf ./build`, `rm -rf node_modules`) does not
match because the path is a static relative directory.

Critical severity reflects the irreversibility: there is no recovery from
a successful `rm -rf` against system or user data, and the hook execution
context means there's no user-confirmation gate. Active at landing.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Active at landing.
