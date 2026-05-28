# CLAUDE.md — SaferSkills

SaferSkills is **"every AI skill, independently scanned"** — a public, free, Apache-2.0 trust-scoring service for skills, MCP servers, hooks, and plugins across every agent platform (Claude Code, Cursor, Windsurf, GitHub Copilot, Codex CLI, Gemini CLI, Cline, OpenClaw). Anyone submits a GitHub URL → 30-second deterministic scan → public Yuka-style report with full rule trace, vendor right-of-reply, and a permalink.

**Architecture (post-W3, Track A/B/D shipped)**: catalog ingestion (`services/api/app/ingestion/`) → scan engine (`services/api/app/scan/` + detector rules under `rubric/`) → public report surface (`webapp/` Astro SSG, indexed by `saferskills.ai/items/<slug>`) → CLI gate (`cli/` npx). Until W3, this repo is the **foundation shell** — codegen pipeline, FastAPI `/health`, Astro placeholder homepage with email capture, design-system tokens.

**Stewardship**: SaferSkills is an OpenLatch project, brand-independent. Footer attribution only — never cross-recommend OpenLatch from a SaferSkills surface. See `.claude/rules/design-system.md` § Anti-recommendation.

---

## Quick Start

```bash
docker compose up                       # postgres + api + webapp (W1 default)
```

Local dev (no Docker):
```bash
# Backend
cd services/api && uv sync && uv run uvicorn app.main:app --reload

# Frontend
cd webapp && pnpm install && pnpm dev

# Codegen
pnpm run generate                       # runs all 7 generators
```

---

## Essential Commands

```bash
# Frontend (webapp/ + ui/)
pnpm dev                                # Astro dev server
pnpm test                               # Vitest
pnpm biome check --write .              # Lint + format
pnpm tsc --noEmit                       # Type check

# Backend (services/api/)
uv run uvicorn app.main:app --reload    # Dev server
uv run pytest tests/ -x                 # Tests
uv run ruff check . --fix && uv run ruff format .   # Lint + format
uv run pyright                          # Type check

# Monorepo (root)
pnpm run generate                       # 7 generators (Pydantic + SQLAlchemy + openapi.json + TS DTO + Zod + methodology MDX from rubric/)
pnpm run lint                           # Biome on all TS/JS/JSON
```

After any code change touching shipped layers, run `/verify-build` — it auto-detects changed layers and runs the right gates.

---

## Design Principles (Non-Negotiable)

1. **Schema-Driven Everything.** Two sources of truth: JSON Schema (`schemas/*.schema.json`) for entity shapes, FastAPI's `app.openapi()` for endpoint DTOs. Generated code under any `generated/` directory is **never edited manually**. See `.claude/rules/schema-driven-development.md`.
2. **Public single-tenant service.** No org isolation at W1 (auth lands W5 / Track E). Public submissions in, public scan reports out. Adversarial-input handling at every system boundary. See `.claude/rules/security.md`.
3. **Methodology over opinion.** Every detection rule is documented in `rubric/` with rule_id (`SS-<CATEGORY>-<NUMBER>`), trigger, severity, FP-review history. Closed-source rules are not allowed. See `docs/methodology.md` + `.claude/rules/methodology.md`.
4. **Vendor right-of-reply is structural.** Every public verdict is appealable; every verified appeal gets a substantive public response within 1 hour. See `.claude/rules/vendor-appeals.md`.
5. **Scope discipline.** Build what's needed now. Extension points (nullable fields, metadata JSONB) for future capabilities. No speculative features.

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | TypeScript (strict), Astro 6 + React 19 islands, Tailwind v4, shadcn/ui (Radix + Tailwind v4), Biome, Vitest, pnpm 10. (Astro instead of Vite is a deliberate divergence vs openlatch-platform — public SSG catalog needs SEO + Lighthouse + share-preview, see `.claude/rules/tech-stack.md` § Frontend.) |
| **Backend** | Python 3.14, FastAPI, Pydantic v2, Ruff + pyright, uv, pytest, SQLAlchemy 2 (async), Alembic |
| **Detection** (W2+) | In-process deterministic rules under `rubric/`. **No LLM in the verdict path** — every finding has a static rule_id and a quotable line of evidence. |
| **Data** | PostgreSQL 17, in-process LRU caches (no Redis), PG full-text search + pg_trgm |
| **Infra** | Docker, Docker Compose (self-hosted), GitHub Actions, dual-registry push (ghcr.io archive + registry.fly.io for deploys), Fly.io (production) |
| **Auth** (W5+) | better-auth + magic link + @better-auth/sso (SAML) — deferred to Track E |
| **Observability** | Sentry (errors only) + PostHog (closed-enum event names + bucketed numerics, no PII) + Grafana Cloud (shared stack under `saferskills-*` prefix) + OpenTelemetry |
| **Email** (W5+) | Resend (transactional + audiences) |

Mandates, forbidden tools, and package-manager rules: `.claude/rules/tech-stack.md`.

---

## Monorepo Structure

```
schemas/           # JSON Schema source-of-truth for all data contracts
scripts/           # The 6 codegen scripts + validate-schemas.cjs
services/api/      # FastAPI backend (W1 shell + scan engine from W2)
webapp/            # Astro 6 + React 19 public catalog (placeholder W1, real W3)
ui/                # Design system & shared components (atoms/molecules/organisms)
rubric/            # Detection rules (W2+ — placeholder dir at W1)
cli/               # `saferskills` CLI (W4+ — placeholder dir at W1)
tools/e2e/         # Playwright + Python e2e command suite
.claude/rules/     # Domain-specific rules (path-scoped — load only when relevant files are edited)
.github/           # Workflows, ISSUE_TEMPLATEs, CODEOWNERS, dependabot, labels
```

Reusable cross-app components → `ui/components/`. Webapp-specific components → `webapp/src/components/`. Reuse or extend before creating new ones. See `ui/CLAUDE.md` and `.claude/rules/design-system.md`.

---

## Adding New Features

Once Track A/B ships, the canonical pattern for adding a new entity (e.g. a new ingestion source) is the same `/add-entity` flow used in openlatch-platform: JSON Schema → `pnpm run generate` → migration → router → frontend → navigation → tests.

For new detection rules: open a `.github/ISSUE_TEMPLATE/03-rule-proposal.yml` RFC first. Do NOT land a rule without an RFC.

---

## Conventions

- **Commits**: Conventional Commits — `type(scope): description`.
- **Package managers**: `pnpm` (frontend/TS), `uv` (backend/Python) — never mix.
- **Naming**: API JSON snake_case, response models inherit `OrmBaseModel`, paginated responses use `data` (not `items`). Rule IDs `SS-<CATEGORY>-<NUMBER>`. Full rules: `.claude/rules/naming-conventions.md`.

---

## Brand independence (Non-Negotiable)

SaferSkills and OpenLatch share stewardship and (deliberately) share teal — distinction-by-shape, not by color:
- SaferSkills primary: emerald teal `#0D9488` — **kinship-by-color** with the OpenLatch master palette per Wordmark Spec lock 2026-05-27. The original cobalt-primary direction is superseded.
- Distinction-by-shape: chamfered hex-cap button vocabulary, page-head + ridge dividers, DM Sans / Space Mono / Anybody / Nanum Pen Script type stack, monochrome Onest 600 wordmark — none of which OpenLatch uses.
- SaferSkills voice: methodology-over-opinion, anti-recommendation, never cross-promotes.
- Footer attribution ("An OpenLatch project") is the only OpenLatch mention allowed on SaferSkills surfaces.
- Outbound system email ships from `notifications.openlatch.ai` — a single Resend verified sending domain shared with OpenLatch (cost decision 2026-05-28). Display name stays `SaferSkills`; reply-to is always a `@openlatch.ai` mailbox. Disclosed on `/about`.
- Enforced in PR review on every README / homepage / catalog-copy change. See `.claude/rules/design-system.md`.

---

## In-flight chores

- Reactivate the schema-to-code drift gate once `openlatch-client-schemas`-equivalent is published for SaferSkills wire schemas (Track A W3).
- Dependabot weekly bumps land Monday morning; review them in the PR queue.

---

## Domain-Specific Rules

`.claude/rules/*.md` files load contextually via `paths:` frontmatter — only when files matching the patterns are read. Always-on (no `paths:`): `security.md`, `naming-conventions.md`, `ci-cd.md`, `documentation-sync.md`, `tech-stack.md`.

Deferred rules (added when the corresponding feature lands — see `.claude/rules/documentation-sync.md`):
- `multi-tenancy.md` / `database.md` / `security-auth.md` (W5 with auth)
- `routing-engine.md` / `config-plane.md` (NEVER — these are OpenLatch-Platform-specific)
- `client-schemas-sync.md` (if cross-repo schemas arrive)
