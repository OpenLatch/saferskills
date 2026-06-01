# Documentation Sync

**Documentation that contradicts the code is worse than no documentation.** Updates ship in the same PR as the code change.

## Rule files at W1

12 forks + 3 SaferSkills-specific rules live under `.claude/rules/`.

| Always-on (no `paths:` frontmatter) | Path-scoped |
|---|---|
| `security.md` | `schema-driven-development.md` (`schemas/**`, `scripts/generate-*.cjs`, generated dirs) |
| `naming-conventions.md` | `generated-code.md` (`**/generated/**`) |
| `ci-cd.md` | `design-system.md` (`ui/**`, `webapp/src/components/**`) |
| `documentation-sync.md` | `testing.md` (test dirs + `tools/e2e/**`) |
| `tech-stack.md` | `telemetry.md` (`services/api/app/**`, `webapp/src/**`, `ui/**`) |
| | `environment-config.md` (env files + `app/core/config.py`) |
| | `frontend-patterns.md` (`webapp/**`, `ui/**`) |
| | `methodology.md` (`docs/methodology.md`, `docs/rules.md`, `rubric/**`) |
| | `vendor-appeals.md` (vendor-appeal templates + flows) |
| | `database.md` (`services/api/migrations/**`, `app/models/**`, `app/db/**`) |

## Deferred rules (write when the feature lands)

| Rule | Lands with |
|---|---|
| `security-auth.md` | Track E (W5) — auth, magic links, account routes |
| ~~`database.md`~~ | **Written** (migration `0006_add_artifact_blobs` — first content-storage subsystem). Now active above. |
| `multi-tenancy.md` | NEVER at W1 — SaferSkills is single-tenant public. Only write if the product pivots to multi-tenant. |
| `client-schemas-sync.md` | If a cross-repo wire-format package is published (no plans at W1) |
| `routing-engine.md` / `policy-engine.md` / `config-plane.md` | NEVER — SaferSkills has no detection plane / routing engine; scans are CI-driven, not request-driven |
| `editor-governance.md` | NEVER — no marketplace / editor capability |
| `activity-digest.md` | If a per-vendor digest feature ships (not in current roadmap) |
| `data-seed.md` | If a `tools/data-seed/` CLI is added |
| `admin-broadcasts.md` | If site-wide admin broadcasts ship |

## Path-scoped vs always-on

- **Always-on rules** load on every interaction — keep them under 150 lines and reference path-scoped rules for detail.
- **Path-scoped rules** declare `paths:` frontmatter and load only when files matching the pattern are edited.
- Never put domain detail in an always-on rule that would force-load it on every prompt; extract to a path-scoped file.

## Same-PR requirement

| Change Type | Files to check |
|-------------|---------------|
| New component in `ui/components/` | `ui/CLAUDE.md`, root `CLAUDE.md` if it's a new molecule/organism category |
| New route/page in `webapp/` | `webapp/src/lib/nav-config.tsx`, root `CLAUDE.md` if structural |
| New non-homepage page in `webapp/` | Must use the template: `PageHead` + `PageRidge` (new `variant`) + alternating `.page-section` bands — see `design-system.md` § Section surfaces |
| New CLI command/script | Root `CLAUDE.md` + `scripts/README.md` |
| New service in `services/` | `tech-stack.md`, `environment-config.md`, root `CLAUDE.md` |
| DB schema/migration change | `database.md` + the model under `app/models/` + the registry import in `app/models/__init__.py` |
| New stored-content table/column (e.g. `artifact_blobs`) | `database.md` + `security.md` § Vendor-data isolation (retention tier) — re-verify the trace stays no-raw-payload |
| New env var | `environment-config.md`, `services/api/.env.example`, `webapp/.env.example` |
| New rule under `rubric/` | `methodology.md` + the new rule doc + the CI lane that runs it |
| New scan trigger / scan-pipeline change | `methodology.md` + `security.md` (scan-trace transparency) |
| New vendor-appeals lifecycle state | `vendor-appeals.md` + `.github/ISSUE_TEMPLATE/04-vendor-appeal.yml` |
| Codegen pipeline change | `schema-driven-development.md`, `generated-code.md`, `frontend-patterns.md`, `ci-cd.md`, root `CLAUDE.md` |
| Tech stack change (version bump, new dep) | `tech-stack.md` |
| CI lane change | `ci-cd.md` (lanes table) |
| Naming convention change | `naming-conventions.md` |
| Design token change | `design-system.md` + `ui/styles/tokens.css` |
| DS-component CSS added/moved | `ui/styles/components.css` (not page CSS) — see `design-system.md` § CSS ownership |
| `check-css.cjs` rule / scope change | `design-system.md` § CSS token discipline + `scripts/check-css.cjs` + `ci-cd.md` |
| Telemetry event added | `telemetry.md` (event allowlist) |

## Hard rules

1. **Same-PR requirement** — docs ship with code, not as follow-up.
2. **No orphaned references** — grep `.md` files when renaming/moving/deleting.
3. **No speculative docs** — only document what exists now. Deferred rules stay in the table above until the feature lands.
4. **Update, don't duplicate** — integrate into existing structure.
5. **Remove stale content** — contradictory guidance is a violation.
6. **Public docs vs contributor docs are in sync** — `docs/methodology.md` (public-facing) and `.claude/rules/methodology.md` (contributor-facing) cover the same contract; never let them drift.

## When to update this rule

| Change | Updates here |
|---|---|
| New rule file shipped | "Rule files at W1" table — move from deferred to active if applicable |
| New deferred feature mapped | "Deferred rules" table |
| New same-PR doc obligation | "Same-PR requirement" table |
