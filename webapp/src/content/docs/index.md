---
title: "SaferSkills Documentation"
description: "Find, verify, and install AI capabilities; read the methodology behind every scan; run an Agent Scan — across every agent platform."
updated: 2026-06-16
---
SaferSkills independently scans every AI capability — skills, MCP servers, hooks, plugins, and rules — and publishes a public trust score with a full rule trace. These docs teach you to find and verify a capability, install it safely, publish your own and get it scanned, and read the deterministic methodology behind every score. Every verdict here is reproducible: no LLM sits in the scoring path.

## Who are these docs for?

These docs serve anyone who builds with or depends on AI agents. **Developers** installing skills and MCP servers will want the [quickstart](/docs/getting-started/quickstart/) and the [CLI reference](/docs/install/cli-reference/). **Skill and MCP authors** publishing their own work should read [publish and get scanned](/docs/for-authors/publish-and-get-scanned/) and the [right-of-reply](/docs/for-authors/disputing-findings/) process. **Security researchers** auditing the agent ecosystem will go to [how scoring works](/docs/security-and-methodology/how-scoring-works/) and [detection categories](/docs/security-and-methodology/detection-categories/). **CISOs and platform managers** weighing what their teams run should start with [why scanning matters](/docs/getting-started/why-scanning-matters/) and [managing your agents](/docs/concepts/managing-your-agents/).

## Where should you start?

Start with [Getting Started](/docs/getting-started/) if SaferSkills is new to you — it covers [what SaferSkills is](/docs/getting-started/what-is-saferskills/), [why independent scanning matters](/docs/getting-started/why-scanning-matters/), a five-minute [quickstart](/docs/getting-started/quickstart/), and the [core concepts](/docs/getting-started/core-concepts/) that the rest of the docs assume.

## What does each section cover?

- **[Getting Started](/docs/getting-started/)** — the orientation path: what SaferSkills is, why scanning matters, the quickstart, and the core concepts.
- **[Concepts](/docs/concepts/skills/)** — what each capability kind is and how it is scored: [skills](/docs/concepts/skills/), [MCP servers](/docs/concepts/mcp-servers/), [hooks](/docs/concepts/hooks/), [plugins](/docs/concepts/plugins/), the [scoring overview](/docs/concepts/how-scoring-works/), [the Agent Scan](/docs/concepts/agent-scan/), and the [glossary](/docs/concepts/glossary/).
- **[Find & Verify](/docs/find-and-verify/browse-the-catalog/)** — use the running service: [browse the catalog](/docs/find-and-verify/browse-the-catalog/), [scan a repo](/docs/find-and-verify/scan-a-repo/), [read a scan report](/docs/find-and-verify/read-a-scan-report/), and [embed your badge](/docs/find-and-verify/embed-your-badge/).
- **[Agent Scan](/docs/agent-scan/what-agent-scan-is/)** — the behavioral pack that grades a running agent rather than its static files: [what it is](/docs/agent-scan/what-agent-scan-is/), [run one](/docs/agent-scan/run-an-agent-scan/), [read the report](/docs/agent-scan/read-an-agent-report/), and the [behavioral scoring model](/docs/agent-scan/behavioral-scoring/).
- **[Install](/docs/install/install-a-skill/)** — the `saferskills` CLI: [install a skill](/docs/install/install-a-skill/), the [command reference](/docs/install/cli-reference/), [global flags](/docs/install/global-flags/), and per-agent guides for all eight supported platforms.
- **[For Authors](/docs/for-authors/publish-and-get-scanned/)** — get your capability indexed and scored: [publish and get scanned](/docs/for-authors/publish-and-get-scanned/), the [SKILL.md spec](/docs/for-authors/skill-md-spec/), [claim your repo](/docs/for-authors/claim-your-repo/), and [disputing findings](/docs/for-authors/disputing-findings/).
- **[Security & Methodology](/docs/security-and-methodology/how-scoring-works/)** — the deep methodology: [how scoring works](/docs/security-and-methodology/how-scoring-works/), the [five sub-scores](/docs/security-and-methodology/5-sub-scores/), [detection categories](/docs/security-and-methodology/detection-categories/), [finding evidence](/docs/security-and-methodology/finding-evidence/), and how to [contribute a rule](/docs/security-and-methodology/contribute-a-rule/).
- **[Reference](/docs/reference/api/)** — the [public API](/docs/reference/api/), the [FAQ](/docs/reference/faq/), and [about](/docs/reference/about/) the project.

## How can you check the rules yourself?

Every detection rule is documented and auto-rendered on the live [methodology page](/methodology), with its severity, sub-score, framework references, and a permalink to the rule source. You can [browse the catalog](/catalog), [submit a scan](/scan), or open the [Agent Report directory](/agents) on the main site at any time — the docs and the running service share one source of truth.

## Where can you get help?

Have a question these docs don't answer? [Join our community Slack](/slack) to ask the maintainers and other users, or open a thread in [GitHub Discussions](https://github.com/OpenLatch/saferskills/discussions).
