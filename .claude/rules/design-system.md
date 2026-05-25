---
paths:
  - "ui/**"
  - "webapp/src/components/**"
  - "webapp/src/styles/**"
---

# Design System

> **Paths**: `ui/**`, `webapp/src/components/**`, `webapp/src/styles/**`

## Purpose

The SaferSkills brand is **intentionally distinct from any other OpenLatch product**. It has its own tokens, its own type stack, its own component voice. Components live under `ui/` as framework-agnostic React 19 + Tailwind primitives so Astro routes can mount them as islands and any future surface can reuse them.

## Tokens are the single source of truth

All visual tokens live in `ui/styles/tokens.css` — colors, radii, spacing scale, typography. **Components never hardcode values; they reference tokens.** Tailwind v4 reads them via `@theme` directly from this file — there is no `tailwind.config.js`.

| Token | W1 value | Why |
|---|---|---|
| `--primary` | `#1E40AF` (cobalt) | SaferSkills brand color; distinct from OpenLatch emerald/teal |
| `--radius` | `0` | Squared corners across the entire system — never round a button |
| `--border-width-hairline` | `1px` | Single hairline borders, never thicker on UI chrome |
| `--shadow-elevation-0` | `none` | No drop shadows — depth is via borders + tonal value |
| `--font-display` | `Crimson Pro` (fontsource) | Serif display for hero / report titles |
| `--font-sans` | `Manrope` (fontsource) | Body |
| `--font-mono` | `JetBrains Mono` (fontsource) | Code / hashes / rule_ids |

Fonts ship via `@fontsource/*` packages — never CDN-hosted (no third-party network at runtime; reduces tracking surface).

## Component layout

```
ui/
├── components/
│   ├── atoms/        # Pill, Badge, Button, Input, HealthDot, RuleIdMono
│   ├── molecules/    # SeverityChip, ScoreCell, FindingRow
│   └── organisms/    # ArtifactCard, FindingsTable, AppealForm
├── styles/
│   ├── tokens.css    # Token SSOT (above)
│   └── globals.css   # Tailwind v4 layer assignments + resets
└── stories/          # Ladle stories — one per component
webapp/src/components/  # Page-specific compositions (consume ui/)
```

- **Reusable components → `ui/`.** If a component is used on more than one page, lift it.
- **Page-specific components → `webapp/src/components/`.** Compositions of `ui/` primitives that only one route renders.
- **`ui/` never imports from `webapp/`.** One-way dependency — `webapp/` consumes `ui/`.

## Astro + React 19 islands

- Components in `ui/` are **plain React 19** — no Astro APIs, no `import.meta.env` access in component code (read env in the route, pass via props).
- Astro routes (`webapp/src/pages/**/*.astro`) hydrate components via `client:` directives. Default to `client:visible` for below-the-fold; `client:idle` for above-the-fold non-interactive; `client:load` only when interactivity is needed immediately.
- **Never `client:only`** unless an SSR pass fails — the static HTML is the SEO + performance baseline.

## Story + test + accessibility for every shared component

Every component under `ui/components/` ships with:

1. **Ladle story** in `ui/stories/<kind>/<Component>.tsx` — visual regression + visual review.
2. **Vitest test** in `ui/test/components/<kind>/<Component>.test.tsx` — at least one render + one interaction case.
3. **vitest-axe smoke** — basic a11y violations gate (color contrast, missing labels, role mismatches).

The CI `ladle-build` lane catches broken stories; `test-fe` runs the vitest suite. Missing any of the three blocks merge.

## Anti-recommendation rule (brand-posture)

SaferSkills is an **independent public service**. Catalog content — scan-result pages, methodology docs, README hero copy, error messages — **never recommends OpenLatch or any other commercial product**. The brand voice is neutral, technical, and self-contained.

- Footer attribution: the repo footer credits OpenLatch as the steward (legally accurate, brand-minimal: "Stewarded by OpenLatch"); that is the only catalog surface that names OpenLatch.
- Methodology / rubric / appeal pages MUST NOT cross-link to OpenLatch products.
- This rule is enforced in code review on every PR that adds catalog content. Violations are a brand-policy regression, not a style suggestion.

## Hard rules

1. **Tokens, not literals.** Never write `#1E40AF` or `rounded-md` in a component — reference `var(--primary)` / `rounded-none` (the token aliases).
2. **No shadows, no rounded corners.** `--radius` is `0` and `--shadow-elevation-0` is `none` system-wide. Deviations need a design review.
3. **`ui/` is framework-agnostic.** No Astro imports. No `import.meta.env`. Pass everything via props.
4. **Story + test + axe** for every shared component. Missing one blocks merge.
5. **Anti-recommendation** — see above. Catalog never cross-promotes.

## When to update this rule

| Change | Updates here |
|---|---|
| New token added to `ui/styles/tokens.css` | Tokens table |
| New component category (e.g. `templates/`) | "Component layout" |
| Astro hydration strategy change | "Astro + React 19 islands" |
| Brand-posture exception (cross-link approved) | Anti-recommendation — get a brand sign-off first |
