---
ruleId: SS-HOOKS-OBFUSCATION-EVAL-01
severity: high
subScore: security
weight: 25
status: active
shadowUntil: null
appliesTo: [hooks]
title: >-
  Hook builds and runs commands at runtime with eval
categoryLabel: >-
  Obfuscation
explanation: >-
  This hook runs automatically on an agent event. The spotted command <code>{match}</code>
  uses <code>eval</code> on command-substituted or variable content — the actual code is
  assembled at runtime from values not visible in the source, defeating any static review.
severityRationale: >-
  the executed code is built from runtime values, so what actually runs can't be reviewed in the source.
remediation:
  action: >-
    Replace eval with explicit commands so the executed code is visible in the source.
  steps:
    - >-
      Rewrite <code>eval</code> as a direct call with explicitly constructed, reviewable arguments.
    - >-
      If a value must come from the environment, validate it before use instead of eval-ing it.
  saferPattern:
    before: |-
      eval "$(get_cmd)"
    after: |-
      cmd="$(get_cmd)"
      case "$cmd" in build|test|lint) "$cmd" ;; *) exit 1 ;; esac
trigger:
  type: regex_match
  pattern: '(?i)\beval\s+["'']?\$\(.*\)|\beval\s+["'']?[^"''\n]*\$\{?\w+\}?[^"''\n]*["'']?|\bsource\s+<\(.+\)'
  scope:
    paths: ['.claude/hooks/**', 'hooks/**', '**/*.hook.sh', '**/SessionStart*', '**/PreToolUse*', '**/PostToolUse*']
limitations:
  - "Legitimate uses of eval exist (string-substitution before execution); the FP risk is real but the hook-scope filter bounds it."
  - "Cannot detect non-shell eval equivalents (Python exec(), JavaScript eval(), etc.) in hook scripts written in those languages — those would be separate rules."
  - "Cannot detect indirect-eval (functions whose body executes a variable)."
priorArt:
  - https://owasp.org/www-community/attacks/Command_Injection
  - https://attack.mitre.org/techniques/T1027/
  - https://cwe.mitre.org/data/definitions/95.html
---

# SS-HOOKS-OBFUSCATION-EVAL-01 — `eval` with dynamic content in hook

## Rationale

`eval` with command-substituted (`$(...)`) or variable-interpolated content
in a hook is dynamic code construction at runtime — defeats static review
because the actual code that runs depends on values not visible in the
source. CWE-95 (Eval Injection) and the OWASP command-injection guidance
classify this as a baseline injection vector.

In hook scope, the legitimate use cases are narrow (string substitution
before execution can usually be rewritten with explicit construction).
The high severity reflects the impact class: eval-with-dynamic-content is
a credential-equivalent threat in the hook execution context.

Active at landing under the hook-scope FP justification — the rule does
not fire on `eval "static string"` (no dynamic content) and does not
trigger outside the hook directory tree.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
