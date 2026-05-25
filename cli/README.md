# cli/ — `saferskills` command-line tool

The CLI scaffolds here from W4 (Initiative I-05 / Track C). The language is **TypeScript** (per locked decision D-09 in `.local/.brainstorms/foundation/plan/INDEX.md`) — Node 24 LTS plus either `@yao-pkg/pkg` or Node 24's stable single-executable-applications (SEA) workflow for the shipped binary.

## Planned commands (W4-8)

```bash
saferskills check <github-url|npm-name>      # 30-second public scan; prints aggregate score + tier
saferskills install <github-url|npm-name>    # gates install on configurable threshold (default: block Red)
saferskills watchlist add <id>                # subscribe (auth lands W5)
saferskills watchlist list
saferskills login                             # SSO / magic link (W5+)
```

## Status

**W1: placeholder.** This directory exists so the repo skeleton is complete and Track C has somewhere to land its work day 1 of W4. Real package + entrypoint land then.

## Why TypeScript (D-09)

The PRD originally referenced Rust for the CLI. Build Plan W3 explicitly leaves the call open. SaferSkills' CLI is install-frequency-dominated (developers run it once when adding a skill), not install-time-dominated (the per-call latency budget is tens-of-ms not microseconds). TypeScript ramps faster, mirrors `@openlatch/client`'s distribution UX, and gives us shared TS types with the webapp via the `webapp/src/generated/openapi/types.gen.ts` contract. Acceptable trade: a ~30-40 MB binary vs Rust's ~5 MB; re-evaluate W5 if friction surfaces.
