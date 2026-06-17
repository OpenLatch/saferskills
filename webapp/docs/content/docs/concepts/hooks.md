---
title: "Hooks"
description: "Hooks are shell commands an agent runs on lifecycle events — a high-risk surface for RCE and exfiltration, with full scanning on the v1.2 roadmap."
updated: 2026-06-16
---
A hook is a shell command an agent runs automatically when a lifecycle event fires — before a tool runs, after a file is written, on session start, and so on. Because a hook executes real shell with the agent's privileges and no further confirmation, it is the highest-risk [capability](/docs/concepts/glossary/#capability) kind: a single line can pull and run remote code, wipe files, or exfiltrate secrets. Hook detection rules ship in the rubric, with full scanning on the v1.2 roadmap.

## What is a hook?

A hook binds a shell command to an agent lifecycle event. In Claude Code, hooks live in a configuration file (for example `~/.claude/settings.json`) and fire on events the agent emits while it works. The command runs on your machine, with your permissions, as part of the agent's normal operation — which is exactly what makes hooks powerful and dangerous in equal measure.

Hooks are a Claude Code-family capability; they are compatible with Claude Code and OpenClaw. See the [glossary](/docs/concepts/glossary/#hook) for the short definition.

## Why are hooks high-risk?

A hook is code that runs without asking. That removes the human checkpoint that normally sits between an instruction and its execution, so the worst-case outcomes are immediate:

- **Remote code execution.** A `curl … | bash` one-liner in a hook fetches a remote script and runs it unreviewed — every later edit to that remote URL re-executes on your machine. SaferSkills flags this with `SS-HOOKS-RCE-CURL-PIPE-01` (`critical`). Related rules cover a destructive `rm -rf` (`SS-HOOKS-RCE-RMRF-01`), unattended `sudo` (`SS-HOOKS-RCE-SUDO-UNATTENDED-01`), and a reverse-shell egress pattern (`SS-HOOKS-RCE-NET-EGRESS-01`).
- **Obfuscated payloads.** A hook can hide its intent behind encoding — a `base64 -d | bash` decode-and-run, caught by `SS-HOOKS-OBFUSCATION-B64-SHELL-01`, or a dynamic `eval`, caught by `SS-HOOKS-OBFUSCATION-EVAL-01`.
- **Exfiltration.** The same shell access that runs a build step can read a secret and POST it to an attacker endpoint.

Remote-code-execution patterns like these are why a hook deserves more scrutiny than any other capability — the [Sonatype 2024 State of the Software Supply Chain Report](https://www.sonatype.com/state-of-the-software-supply-chain/introduction) recorded a 156% year-over-year rise in malicious open-source packages, and an auto-executing hook is the most direct delivery vehicle for one.

## How does SaferSkills handle hooks?

The HOOKS detection category exists in the rubric today — its rules map to the [detection categories](/docs/security-and-methodology/detection-categories/) and use the same [`rule_id`](/docs/concepts/glossary/#rule_id) grammar (`SS-HOOKS-<NAME>-NN`) and the same [severity tiers](/docs/concepts/glossary/#severity-tier) as every other category. Skills and MCP servers are the fully scanned capabilities in v1; broader hook coverage is a forward-looking item on the v1.2 roadmap. The scoring model is unchanged when it lands: an active `critical` finding such as a `curl | bash` hook caps the whole aggregate at ≤15, and a low score means **review the command before you let it run**.

## Related reading

- [Detection categories](/docs/security-and-methodology/detection-categories/) — the closed set of five, including HOOKS.
- [Glossary](/docs/concepts/glossary/) — definitions for [hook](/docs/concepts/glossary/#hook), [severity tier](/docs/concepts/glossary/#severity-tier), and [finding](/docs/concepts/glossary/#finding).
- [Plugins](/docs/concepts/plugins/) — a bundle that can ship hooks alongside other capabilities.
