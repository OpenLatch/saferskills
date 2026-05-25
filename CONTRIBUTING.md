# Contributing to SaferSkills

Thanks for your interest in contributing! SaferSkills is an Apache-2.0, public, free trust-scoring service for AI-agent artifacts. We welcome code, detection-rule proposals, vendor appeals, bug reports, and translations.

## Code of Conduct

This project adopts the [Contributor Covenant 3.0](./CODE_OF_CONDUCT.md). Enforcement contact: `conduct@openlatch.ai`.

## Prerequisites

- **Node.js 24 LTS** (`.nvmrc`)
- **Python 3.14** (`.python-version`)
- **pnpm 10**
- **uv** (latest)
- **Docker** + Docker Compose
- Optional: **`pre-commit`** for the local hook stack (`pip install pre-commit`)

## Setup

```bash
git clone https://github.com/OpenLatch/saferskills.git
cd saferskills
pnpm install
pre-commit install                         # secrets + lint hooks
docker compose up -d                       # postgres + api + webapp
pnpm run generate                          # 6 codegen scripts
cd services/api && uv sync && cd ../..
```

Verify:
```bash
curl http://localhost:8000/api/v1/health   # → {"status":"ok",...}
open http://localhost:5173                 # → placeholder homepage
```

## Branch naming

`<type>/<short-slug>` — e.g. `feat/scoring-engine`, `fix/health-endpoint-encoding`, `chore/bump-dependabot`, `docs/contributing-clarify`. `<type>` mirrors Conventional Commits.

## Commits

**Conventional Commits + DCO required.**

```
<type>(<optional scope>): <short imperative summary>

<optional longer body>

Signed-off-by: Your Name <your@email>
```

Use `git commit -s` to auto-add the DCO trailer. CI's `dco-check` job blocks PRs that miss it on any commit.

Allowed `<type>`: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`, `style`. PR titles enforce the same set (`pr-title-lint.yml`).

## Pull requests

1. Fork + branch off `main`.
2. Make the change. Keep PRs focused — one concern per PR.
3. Run the local quality gates before pushing:
   ```bash
   pnpm biome check --write .
   pnpm tsc --noEmit
   pnpm test
   cd services/api && uv run ruff check . --fix && uv run pyright && uv run pytest
   ```
4. Push + open a PR. The PR template will guide you.
5. CI runs 14 lanes. All `all-checks` are required to pass. The PR can land **green-only**.

## Detection-rule contributions (rule-RFC)

Detection rules are not landed via direct PR. Open a **`03-rule-proposal.yml`** issue first:
- The trigger (pseudo-code + the exact regex / AST query you'd use)
- The severity tier with rationale (`Low / Medium / High / Critical`)
- A positive fixture (artifact that should fire the rule)
- A negative fixture (artifact that looks similar but should NOT fire)
- "What this rule cannot catch" — the limitations doc the rubric requires
- Any vendor impact you anticipate (will it cascade onto N existing catalog items?)

The community + maintainers comment for **7 days**. Maintainer decision is public. If approved, the PR landing the rule adds `rubric/<rule_id>.json` + a unit test + the two fixtures.

Full lifecycle: `METHODOLOGY.md` + `.claude/rules/methodology.md`.

## Vendor appeals

If you maintain an item that SaferSkills has scanned and you believe the verdict is wrong / out of scope / mis-applied, **do not open a regular issue**. Open a **`04-vendor-appeal.yml`**. We commit to a substantive public response within 1 hour for verified maintainers. See `.claude/rules/vendor-appeals.md`.

## Tests

- Frontend (Vitest): every public component gets a smoke test + a vitest-axe smoke. Coverage gate: ≥70% line coverage on `webapp/` + `ui/` packages.
- Backend (pytest): every router gets a happy-path + an adversarial-input test. Coverage gate: ≥70% line coverage on `services/api/`.
- E2E (Playwright via `tools/e2e/`): `doctor + smoke + homepage` at W1; per-feature commands grow with each track.

A bug fix lands with a regression test that fails on `main` and passes on the branch.

## Documentation

If your PR changes shipped behavior, update:
- The relevant `.claude/rules/<rule>.md` (look up paths via `paths:` frontmatter)
- The user-facing surface (`README.md`, `METHODOLOGY.md`, `RULES.md`, the relevant page in `webapp/src/pages/`)

See `.claude/rules/documentation-sync.md`.

## Releases

Release Please opens release PRs from Conventional Commits. Merging the release PR cuts a tag, builds + signs the artifacts (cosign keyless + SLSA L3 + CycloneDX + SPDX SBOMs), and publishes them.

## Security

If you find a security issue in SaferSkills itself, **do not open a public issue**. Use GitHub Private Vulnerability Reporting or email `security@openlatch.ai`. See `SECURITY.md`.

Concerns about a verdict on an item SaferSkills *scanned* are not security issues — file a vendor appeal instead.

## Questions

GitHub Discussions is the public Q&A surface: <https://github.com/OpenLatch/saferskills/discussions>.

Thanks for contributing. — The SaferSkills maintainers
