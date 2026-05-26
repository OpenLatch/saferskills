# `@openlatch/saferskills` — CLI

> The VirusTotal of AI agents — **coming soon, mid-2026**.

SaferSkills is a public, free, Apache-2.0 trust-scoring service for AI-agent skills, MCP servers, hooks, and plugins. Once the first functional release lands you'll use the CLI to:

```bash
saferskills check <github-url|npm-name>     # 30-second public scan; prints aggregate score + tier
saferskills install <github-url|npm-name>   # gates install on configurable threshold (default: block Red)
saferskills watchlist add <id>              # subscribe (auth lands W5)
saferskills watchlist list
saferskills login                           # SSO / magic link (W5+)
```

For source, methodology, and progress: [github.com/OpenLatch/saferskills](https://github.com/OpenLatch/saferskills). For the public catalog (live mid-2026): [saferskills.ai](https://saferskills.ai).

---

## Status (W1)

**Placeholder.** This package is a name reservation — installing it currently does nothing functional. The first functional release lands W4–8 (Initiative I-05 / Track C of the SaferSkills build plan).

## Language: TypeScript (decision D-09)

Per locked decision D-09 in `.local/.brainstorms/foundation/plan/INDEX.md`, the CLI is TypeScript on Node 24 LTS, shipped as a single-executable-application (SEA) — not Rust. SaferSkills' CLI is install-frequency-dominated (developers run it once per skill they add), not per-call-latency-dominated, so TypeScript ramps the feature surface faster, mirrors `@openlatch/client`'s distribution UX, and shares TS types with the webapp via the generated `webapp/src/generated/openapi/types.gen.ts` contract. Trade-off accepted: a ~30–40 MB binary vs Rust's ~5 MB; re-evaluated W5 if friction surfaces.

## Publishing

This package is published via [npm Trusted Publishers (OIDC)](https://docs.npmjs.com/trusted-publishers) — no long-lived `NPM_TOKEN` secret in CI. The release path is `.github/workflows/publish-npm.yml`, bound to the `npm-publish` GH Environment. See that workflow's header comment for the binding contract.
