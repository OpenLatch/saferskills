<div align="center">

![SaferSkills banner](./webapp/public/banner.png)

# SaferSkills

**The VirusTotal of AI agents.** Free, public, open-source trust scoring for skills, MCP servers, hooks, and plugins — across every agent platform.

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-1E40AF.svg)](./LICENSE)
[![CI](https://github.com/OpenLatch/saferskills/actions/workflows/pr-checks.yml/badge.svg)](https://github.com/OpenLatch/saferskills/actions/workflows/pr-checks.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/OpenLatch/saferskills/badge)](https://securityscorecards.dev/viewer/?uri=github.com/OpenLatch/saferskills)
[![Project status](https://img.shields.io/badge/status-v0.x_pre--launch-orange.svg)](#project-status)
[![Discussions](https://img.shields.io/github/discussions/OpenLatch/saferskills)](https://github.com/OpenLatch/saferskills/discussions)

[saferskills.ai](https://saferskills.ai) · [Methodology](./METHODOLOGY.md) · [Discussions](https://github.com/OpenLatch/saferskills/discussions) · [Security](./SECURITY.md)

</div>

---

## Why

You install a Claude skill, an MCP server, a Cursor rules file, or a Codex hook. It runs with your file-system access. It can read your `.env`. It can `curl | bash`. It can ship your repo to a paste site. There is **no public, transparent record** of what each of those tens of thousands of items actually does.

SaferSkills is that public, transparent record. Anyone — a developer, a vendor, a researcher — can submit a GitHub URL. A 30-second scan returns a digestable security report: aggregate trust score (0–100), four-tier breakdown (Identity / Integrity / Behavior / Provenance), every detector that fired, the rule that fired it, the exact line of evidence, the remediation, and a permalink that vendors can dispute.

Methodology, not opinion. Every rule is documented. Every score is reproducible. Every appeal is public.

## Quick start

```bash
# Install (W4+, once the CLI ships)
npx saferskills check github.com/some-author/some-mcp-server
npx saferskills install github.com/some-author/some-mcp-server   # only installs if score ≥ threshold

# Or browse the catalog at
open https://saferskills.ai
```

> v0.x — building publicly through 2026-08. The CLI is not yet shipped (Track C, W4). At W1, this repo exists, the codegen pipeline runs end-to-end, and `saferskills.ai` resolves to a placeholder. See [Project status](#project-status).

## How it works

```
┌───────────────────┐    ┌──────────────────────┐    ┌───────────────────┐
│ Public catalog    │    │ Scan engine          │    │ Public scan report│
│ (GitHub URL in)   │───▶│ • Identity / sig     │───▶│ 0–100 score       │
│                   │    │ • Integrity / fuzz   │    │ 4-tier breakdown  │
│ ~30k items at GA  │    │ • Behavior / pattern │    │ Every rule + line │
│                   │    │ • Provenance / chain │    │ Vendor right-of-  │
│                   │    │                      │    │ reply on every    │
│                   │    │                      │    │ deny verdict      │
└───────────────────┘    └──────────────────────┘    └───────────────────┘
```

## Trust score rubric

| Tier | Range | Meaning |
|---|---|---|
| Green | 80–100 | Indexed, signed, behaviorally clean, provenance-verified |
| Yellow | 60–79 | Known author, no critical findings, some lower-severity flags |
| Orange | 40–59 | Anonymous author OR mid-severity finding OR provenance unclear |
| Red | 0–39 | Critical finding (prompt injection / shell RCE / secret exfil / supply-chain) |

Sub-scores are weighted (Identity 25% · Integrity 25% · Behavior 30% · Provenance 20%). Full rubric: [METHODOLOGY.md](./METHODOLOGY.md). Every detection rule: [RULES.md](./RULES.md).

## Use it as

| Mode | Audience | Status |
|---|---|---|
| **Service** — browse `saferskills.ai`, share a permalink | every dev, every researcher | placeholder live W1; real catalog W3 (Track D) |
| **CLI** — `npx saferskills check <url>` | individual installers | W4 (Track C) |
| **Self-host** — `docker compose up` (this repo) | privacy-strict orgs, air-gapped builds | W1 working shell; full scan engine W3 (Track B) |

## Project status

**v0.x — building publicly through 2026-08.** First public release ~2026-08.

Live tracks (see `vault/05-GTM/Launch/SaferSkills - Build Plan.md` if you have vault access, otherwise see [the Initiative summaries](./.local/.brainstorms/foundation/2026-05-25-design.md)):

- ✅ **I-01 — Foundation** (W1) — this repo, CI, brand, legal chassis, codegen, placeholder homepage
- ⏳ **I-02 — Scoring engine** (W2-3 / Track B)
- ⏳ **I-03 — Catalog ingestion** (W2-4 / Track A)
- ⏳ **I-04 — Web catalog + scan-report** (W3-5 / Track D)
- ⏳ **I-05 — CLI** (W4-8 / Track C)
- ⏳ **I-06 — Email + watchlist + B2B intel** (W7-9 / Track E)
- ⏳ **I-07 — Launch headline** (W10)

## Develop

```bash
git clone https://github.com/OpenLatch/saferskills.git
cd saferskills
pnpm install
pnpm run generate     # 6 generators: Pydantic + SQLAlchemy + openapi.json + TS DTO + Zod
docker compose up     # postgres + api + webapp
curl http://localhost:8000/api/v1/health
open http://localhost:5173
```

Requirements: Node 24 LTS, Python 3.14, pnpm 10, uv 0.7+, Docker.

## Contributing

We welcome contributions — code, detection-rule RFCs, scan-report appeals, and translations. Read [CONTRIBUTING.md](./CONTRIBUTING.md), [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md), and [METHODOLOGY.md](./METHODOLOGY.md) first.

Detection-rule proposals go via [the rule-RFC issue template](.github/ISSUE_TEMPLATE/03-rule-proposal.yml). Vendor appeals go via [the vendor-appeal template](.github/ISSUE_TEMPLATE/04-vendor-appeal.yml).

## Security

Vulnerabilities in SaferSkills itself: see [SECURITY.md](./SECURITY.md) (GitHub Private Vulnerability Reporting or `security@openlatch.ai`).

Concerns about **what SaferSkills says about an item it scans** (incorrect verdict, scope dispute, rule misapplication): file a [vendor appeal](.github/ISSUE_TEMPLATE/04-vendor-appeal.yml) or email `appeals@openlatch.ai`. Every appeal gets a substantive public response within 1 hour for verified maintainers.

## License

Apache License 2.0 — see [LICENSE](./LICENSE) and [NOTICE](./NOTICE). Stewarded by [OpenLatch](https://openlatch.ai).
