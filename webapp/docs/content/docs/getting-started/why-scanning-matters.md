---
title: "Why Scanning Matters"
description: "AI capabilities run with your credentials and your shell. Independent scanning catches injection, exfiltration, and supply-chain risk first."
updated: 2026-06-16
author: "SaferSkills Team"
---
Independent scanning matters because an AI capability is not passive data — it is instructions and code that run inside your agent, with your file-system access, your credentials, and your shell. A poisoned skill body or MCP tool description can hijack the agent, exfiltrate secrets, or pull and run remote code. Prompt injection is the single highest-ranked LLM risk, and a vendor attesting to its own safety is not the same as someone independently checking.

## Why is an installed capability different from ordinary data?

A capability is executed, not merely read. When you install a skill, an MCP server, a hook, or a rules file, you are extending what your agent does — and the agent acts on your behalf, with your access. A hook is a shell script that fires on lifecycle events. An MCP server is a process your agent talks to and trusts the responses from. A skill body is text the agent loads as *trusted instructions*. None of these run in a sandbox by default; they run where you run, reading what you can read and writing what you can write.

That is the asymmetry independent scanning addresses. A reasonable developer reviews a dependency before adding it to `package.json`, but agent capabilities are distributed as prose and config across thousands of repositories with no consistent review surface. The capability that summarizes your inbox can also read your `~/.ssh/` directory; the rules file that "improves code style" can also contain an instruction the model silently obeys. The risk is not hypothetical edge behavior — it is the ordinary scope of what these artifacts are allowed to do.

A second asymmetry is volume. The number of published skills, MCP servers, hooks, and rules across the eight supported agents already runs into the tens of thousands, and grows daily. No individual can read every one before installing, and most installers never read any. Independent, automated scanning is the only way to put a consistent, reproducible signal in front of every install — the same signal for the popular capability and the obscure one. SaferSkills' answer is to scan everything it indexes durably and re-evaluate the whole corpus whenever the rubric or engine version advances, so a verdict never silently goes stale against the current methodology.

## Why is prompt injection the central risk?

Because the capability's own text is the attack surface. OWASP ranks **Prompt Injection as LLM01:2025 — the top risk in the OWASP Top 10 for LLM Applications**, for the second consecutive edition ([source](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)). Direct injection is what a user types; **indirect** injection comes from untrusted external content the model reads and treats as instructions. A skill body and an MCP tool description are exactly that kind of content — the agent loads them and acts on them. So an installed capability is not a passive payload; it is a standing channel for indirect [prompt injection](/docs/concepts/glossary/#prompt-injection) into every session that uses it.

This is why a finding like a fenced "run this command" imperative buried in a skill body is scored as a high-severity security issue: SaferSkills treats the capability text as the untrusted-content boundary that OWASP describes. The rule `SS-SKILL-INJECT-FENCED-RUN-01` exists precisely because a runnable block in trusted-instruction text is an injection vector, and it maps to `owasp-llm:llm01` and `mitre-atlas:AML.T0051` so the finding is anchored to a recognized threat rather than an opinion.

## How does MCP tool poisoning actually work?

MCP tool poisoning hides malicious instructions in a tool's *description* — text the model reads but the user usually never sees. Invariant Labs coined the **Tool Poisoning Attack** in April 2025 and published a working proof-of-concept: a poisoned tool description instructed the model to read the user's `~/.cursor/mcp.json` and SSH keys and smuggle them out through the tool's arguments, with the malicious instructions invisible in the normal UI ([source](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)). An "email shadowing" variant silently rerouted outgoing mail. OWASP now lists **MCP03:2025 Tool Poisoning** in its MCP Top 10 ([source](https://owasp.org/www-project-mcp-top-10/)).

The lesson for scanning is concrete: the dangerous part of an MCP server is often not its code but its declared interface. SaferSkills scans the tool descriptions themselves for invisible-Unicode tag-channel payloads (`SS-MCP-POISON-UNICODE-TAG-01`), oversized "description creep," shadow tools, and bidirectional-text smuggling — because that is where the attack lives. A capability can have clean-looking source and still ship a poisoned description that only the model will obey.

## Is open-source malware really at scale?

Yes, and it is industrial. Sonatype's **10th Annual State of the Software Supply Chain Report (2024)** reported a **156% year-over-year increase** in malicious open-source packages, with **704,102+** identified since 2019 ([source](https://www.sonatype.com/state-of-the-software-supply-chain/introduction)). Agent capabilities ride the same open-source distribution rails — npm names, GitHub repos, MCP registries — and inherit the same supply-chain risks: typosquatting, owner-transfer takeovers, and rug-pulls where a trusted package is quietly replaced with a malicious update.

SaferSkills allocates a fifth of the aggregate score to **Supply Chain** for exactly this reason. Rules such as `SS-MCP-SUPPLY-CHAIN-TYPOSQUAT-01` (Levenshtein-near package names), `SS-MCP-SUPPLY-CHAIN-HASH-DRIFT-01` (content-hash drift between scans, the rug-pull signal), and owner-transfer and unsigned-release checks make the supply-chain posture a measured, visible part of every report. The published 2025 MCP-layer CVEs — for example CVE-2025-6514 (mcp-remote RCE), CVE-2025-49596 (MCP Inspector), and CVE-2025-54136 (Cursor) — show the same surface being actively exploited at the protocol layer.

Hash-drift detection matters most because it catches the attack that signature checks at first install cannot: the rug-pull. A capability you reviewed and approved months ago can be quietly replaced upstream with a malicious update, and nothing about its name, stars, or author changes. By recording a content hash and comparing it across scans, SaferSkills makes a silent swap a visible, scored event rather than an invisible one — which is why the durable, re-evaluated coverage described above is a security property and not just an operational convenience.

## Why isn't a vendor's own assurance enough?

Because self-attestation is not independent verification. A vendor saying "our skill is safe" is a claim with no reproducible basis a third party can check, and the incentive to under-report a problem in your own product is obvious. SaferSkills' value is that it is *independent* and *deterministic*: the same input always yields the same score, the methodology is public, and every finding carries a `rule_id` and a quotable line of evidence so a reader can verify it without trusting either the vendor or SaferSkills on faith.

This is also why SaferSkills publishes methodology rather than endorsements. A low score is not a verdict of "malicious" — it means "review before use." The point is to give every installer the same transparent record the vendor has, so the decision is informed rather than blind. Vendors are not silenced by it: every verdict is appealable through the structural [right-of-reply](/docs/for-authors/disputing-findings/), and findings are annotated with the appeal outcome, never silently deleted.

## What does scanning catch before you install?

Scanning surfaces the things a quick `git clone` and skim will miss: invisible Unicode payloads in a tool description, a base64-encoded shell command in a hook, a credential-file read paired with a network call, a typosquatted dependency, or a stale single-author repo with no security policy. Each is mapped to a documented rule and a severity, and the most dangerous classes — prompt injection, obfuscation, remote code execution, and credential exfiltration — sit in the heavily weighted Security sub-score and can trigger the aggregate ceiling on their own.

## Where do you go from here?

Read [core concepts](/docs/getting-started/core-concepts/) to see how the five capability kinds and the trust model fit together, [how scoring works](/docs/security-and-methodology/how-scoring-works/) for the full scoring math, and the [detection categories](/docs/security-and-methodology/detection-categories/) for the rule families that catch each threat. When you are ready to use the service, the [quickstart](/docs/getting-started/quickstart/) walks you through installing a verified capability and reading its score first.

**Author:** SaferSkills Team — methodology maintainers.
