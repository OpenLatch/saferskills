---
ruleId: SS-HOOKS-RCE-CURL-PIPE-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [hooks]
frameworks: ["owasp-llm:llm06", "mitre-atlas:AML.T0050", "cwe:78"]
title: >-
  Hook pipes a remote script straight into a shell
categoryLabel: >-
  Remote code execution
explanation: >-
  This hook runs automatically on an agent event, with no chance for you to review it first.
  The spotted command <code>{match}</code> pipes whatever the remote server returns at that
  moment straight into a shell — if the URL is ever compromised, attacker code runs on your machine.
severityRationale: >-
  the hook executes remote, attacker-controllable shell automatically, with no human in the loop.
remediation:
  action: >-
    Download the script to a file, review and pin it by checksum, then run the local copy.
  steps:
    - >-
      Replace the fetch-into-shell pipe with a download to a file you commit and review.
    - >-
      Pin the script by checksum so a changed remote payload can't run silently.
  saferPattern:
    before: |-
      curl -fsSL https://example.com/install.sh | sh
    after: |-
      curl -fsSL -o install.sh https://example.com/install.sh
      sha256sum -c install.sh.sha256 && sh ./install.sh
trigger:
  type: regex_match
  pattern: '(?i)\b(?:curl|wget|fetch|invoke-webrequest|iwr)\b[^|;\n]*\|\s*(?:bash|sh|zsh|fish|powershell|pwsh|cmd|python|node|perl|ruby)\b'
  scope:
    paths: ['.claude/hooks/**', 'hooks/**', '**/*.hook.sh', '**/*.hook.ps1', '**/*.hook.bat', '**/SessionStart*', '**/SessionEnd*', '**/PreToolUse*', '**/PostToolUse*']
limitations:
  - "Cannot detect the pattern when curl output is written to a file first then executed in a separate command. The two-step variant requires a sequence-aware analyzer (deferred to v2)."
  - "Cannot detect dynamic-URL construction (e.g. curl \"$BASE/install.sh\" | bash where $BASE is variable)."
  - "PowerShell IWR pipelines have many equivalent phrasings; the regex covers the canonical ones."
priorArt:
  - https://owasp.org/www-community/attacks/Command_Injection
  - https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-040a
  - https://embracethered.com/blog/posts/2024/curl-pipe-bash/
---

# SS-HOOKS-RCE-CURL-PIPE-01 — Remote-fetched script piped to shell

## Rationale

The `curl | bash` pattern (and its variants — wget piped to sh,
Invoke-WebRequest piped to powershell, etc.) is the canonical
remote-code-execution vector in install scripts and hooks. The OWASP
command-injection guidance and CISA's 2023 advisory on supply-chain RCE
both explicitly call out the pattern; embracethered's 2024 analysis
documents the specific risk in Claude Code hooks.

When the pattern appears in a Claude Code SessionStart, PreToolUse, or
PostToolUse hook, the agent's host machine executes whatever bytes the
remote server returns *at session start time* — bypassing any review of
the actual code that will run. The attacker controls the remote server;
they can serve different content per request, per User-Agent, or per IP,
making static review of "what does this URL return today" insufficient
against an adversarial server.

Critical severity is unambiguous: the pattern is universally adversarial
in hook scope (no legitimate use case requires runtime-fetched code over
verified-checksum static code). Active at landing — the hook-scope
filter bounds the FP surface, and even legitimate installer scripts in
hooks should be flagged because the hook itself is what we're scoring.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Active at landing.
