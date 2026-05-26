# webapp — SaferSkills public site

Astro 6 + React 19 islands + Tailwind v4 SSG. The W1 surface is the placeholder homepage at `/` plus `/privacy`, `/terms`, `/methodology` stubs.

## Run locally

```bash
cd webapp
pnpm install
pnpm dev               # http://localhost:5173
```

## Build

```bash
pnpm build             # → dist/
```

## Tests

```bash
pnpm test              # Vitest unit + axe smoke
```

Coverage gate: ≥70% on shipped components (W1: just the email-capture island).

## Layout

```
src/
├── pages/                  # Astro routes (file-based)
│   ├── index.astro         # Placeholder homepage + email capture
│   ├── privacy.astro
│   ├── terms.astro
│   └── methodology.astro
├── layouts/
│   └── Base.astro          # HTML shell, fonts, OG + Twitter meta
├── styles/
│   └── global.css          # Tailwind v4 entry + token import
└── generated/              # ← codegen output (never hand-edit)
    ├── openapi/types.gen.ts
    └── zod/index.ts
public/                     # banner.png (light) + banner-dark.png — README hero
                            # + OG/Twitter card; favicon.svg; robots.txt
```

## See also

- `.claude/rules/design-system.md`
- `.claude/rules/frontend-patterns.md`
- `../ui/CLAUDE.md`
