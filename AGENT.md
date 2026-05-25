# SaferSkills — AI Coding Agent Manifest

Start here: read [CLAUDE.md](./CLAUDE.md) — it's the root architecture doc and applies to every AI coding agent (Claude Code, Cursor, Codex CLI, Gemini CLI, Cline, GitHub Copilot, Windsurf, OpenClaw, …).

Then read the path-scoped rules under `.claude/rules/`. Each rule's blockquote header lists the `Paths:` it applies to — open the rules whose paths match the file(s) you're editing.

## Hard rules

1. **Schema-driven everything.** Never edit files under `**/generated/`. Run `pnpm run generate` after editing any `schemas/*.schema.json`.
2. **DCO required on every commit.** `git commit -s` adds the `Signed-off-by:` trailer. PRs without it fail CI.
3. **Conventional Commits.** `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `build:`, `ci:`. PR titles too — enforced by `pr-title-lint.yml`.
4. **No vendored copies of OpenLatch code.** SaferSkills is an independent Apache-2.0 project. If a SaferSkills primitive needs to land in OpenLatch (or vice-versa), it goes through the public release channel — not a hand-port.

## Further guidance

- `CONTRIBUTING.md` — setup, branch naming, the rule-RFC workflow.
- `METHODOLOGY.md` + `RULES.md` — the public scoring rubric (your edits to detection rules need an RFC under `.github/ISSUE_TEMPLATE/03-rule-proposal.yml`).
- `SECURITY.md` — how to report a vuln in SaferSkills itself. Vulns in items SaferSkills *scans* route via the vendor-appeal form, not here.
