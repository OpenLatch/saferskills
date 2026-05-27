---
ruleId: SS-PLUGIN-SECRET-EXFIL-WEBHOOK-01
severity: high
subScore: security
weight: 25
status: shadow
shadowUntil: 2026-W3-end
appliesTo: [plugin]
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

- v1 (Phase A 2026-W2): initial rule. Lands shadow; FP-audit gates promotion.
