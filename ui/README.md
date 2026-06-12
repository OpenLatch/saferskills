# @saferskills/ui — design system

Framework-agnostic React 19 + Tailwind v4 atoms / molecules / organisms, plus the brand tokens.

## W1 surface

- `styles/tokens.css` — the design-token SSOT (cobalt #1E40AF primary, 0px radius, 1px hairlines, scale, scoring colors)
- `components/atoms/Wordmark.astro` — the SaferSkills wordmark in Crimson Pro
- `components/atoms/Footer.astro` — "An OpenLatch project" footer
- `components/atoms/EmailCaptureForm.tsx` — React 19 island; the only client-side JS on the W1 homepage

## Run

```bash
pnpm test                 # vitest + vitest-axe
pnpm ladle:dev            # http://localhost:61000 — story browser
pnpm ladle:build          # static export — also gated in CI on PRs touching ui/
```

## Conventions

- Every public component ships with a Ladle story + a vitest test (with vitest-axe smoke).
- No shadow tokens. No rounded-corner tokens. Editorial precision — see `.claude/rules/design-system.md`.
- Anti-recommendation: SaferSkills surfaces never cross-recommend OpenLatch in catalog content. The `Footer.astro` "An OpenLatch project" is the only OpenLatch reference allowed.
