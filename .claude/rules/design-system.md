---
paths:
  - 'ui/**'
  - 'webapp/src/components/**'
  - 'webapp/src/styles/**'
---

# Design System

## Purpose

The SaferSkills brand sits on the OpenLatch-shared teal palette (kinship-by-color) with a **distinct shape language** (chamfered hex caps + page-head + ridge dividers) and **distinct type stack** (DM Sans / Space Mono / Anybody / Nanum Pen Script + Onest 600 monochrome wordmark). The visual identity is locked per the Wordmark Spec lock 2026-05-27, which **supersedes** the original cobalt-primary direction.

Components live under `ui/` as framework-agnostic React 19 + Tailwind primitives + thin Astro shells; Astro routes mount them as islands.

## Tokens are the single source of truth

All visual tokens live in `ui/styles/tokens.css` — colors, radii, spacing, typography, motion, layout, signature background textures, hex-mask SVGs, score band colors. **Components never hardcode values; they reference tokens via CSS variables or Tailwind v4 utility classes mapped through the `@theme` block.** Tailwind v4 reads them via `@theme` directly from this file — there is no `tailwind.config.js`.

| Token | Value | Why |
|---|---|---|
| `--ol-brand-primary` | `#0D9488` (emerald teal) | SaferSkills brand color; kinship-by-color with OpenLatch master palette per Wordmark Spec lock 2026-05-27 |
| `--ol-brand-primary-dark` | `#0F766E` | Hover / active state |
| `--ol-brand-accent` | `#F97316` (warm orange) | Script-pen accents, ridge-pixel tick markers, hand-written decorations |
| `--score-green` / `--score-yellow` / `--score-orange` / `--score-red` | OpenSSF-style 4-band semantic colors | Tier color language: ≥80 / 60-79 / 40-59 / 0-39 |
| `--radius-0` | `0` | Squared corners across the entire system — never round a button |
| `--radius-xs` | `2px` | Form fields + chips (lone exception) |
| `--radius-pill` | `999px` | Badges only (used sparingly) |
| `--shadow-hairline` | `0 0 0 1px var(--color-ink)` | Single hairline borders, never thicker on UI chrome |
| `--shadow-stamp` | `4px 4px 0 0 var(--color-ink)` | Press-block hover stamp on cards + featured items |
| `--font-display` / `--font-sans` | `DM Sans` (400-800) | Body + display |
| `--font-mono` | `Space Mono` (400, 700) | Code + rule_ids + monospace meta |
| `--font-loud` | `Anybody` (variable, wdth=125, weight=800) | Score numbers + loud stat displays |
| `--font-script` | `Nanum Pen Script` | Hand-written orange accents (e.g. `~30s`, `live`) |
| `--font-wordmark` | `Onest` (SemiBold 600) | Wordmark only (single use, monochrome) |

Fonts ship via `@fontsource/*` packages (DM Sans, Space Mono, Onest, Nanum Pen Script) or `@fontsource-variable/anybody` for the variable-width display weight. **CDN-hosted fonts are forbidden** — the `validate` CI lane greps for `fonts.googleapis.com` and fails on any hit in `ui/styles/`, `webapp/src/styles/`, or `webapp/src/layouts/`.

## Component layout

```
ui/
├── components/
│   ├── atoms/        # Wordmark, Logo, Footer, Button, ButtonPair, GhStar, Chip, Badge, BandPill,
│   │                 # ScoreNumber, DotStrip, Eyebrow, BracketLabel, Input, PageHead, RidgeStars,
│   │                 # RidgeFlow, RidgePixel, ThemeToggle, RotatingHeadline, Toast, CopyButton,
│   │                 # EmailCaptureForm (retained — reused by I-06 magic-link surface)
│   ├── molecules/    # NavBar, CtaBand, AgentMarquee, WhyRow, InstallTabs, ActionCard,
│   │                 # RecentScanCard, TrendScanCard (Phase A1)
│   │                 # CatalogToolbar, CatalogFilterSide, CatalogResultsRow, ScanSplit,
│   │                 # ScanInput, ScanProgressBar, ScanStageCard, ScanReportHero,
│   │                 # SubScoreAccordion, FindingRow, InstallCommandBox (Phase B)
│   │                 # ScoreHistoryChart, InstallActivity, RelatedItems, EmbedBadgeBox,
│   │                 # VendorResponseCard (Phase C)
│   └── organisms/    # (composition shells if needed)
├── styles/
│   ├── tokens.css    # Token SSOT + dark-mode block + Tailwind v4 @theme
│   └── globals.css   # Tailwind v4 import + @fontsource imports + @layer base + .t-* typography
└── stories/          # Ladle stories — one per component
webapp/src/components/  # Page-specific compositions (consume ui/)
webapp/src/styles/      # reset.css + components.css (page-vocabulary CSS, ported from mockup)
```

- **Reusable components → `ui/`.** If a component is used on more than one page, lift it.
- **Page-specific components → `webapp/src/components/`.** Compositions of `ui/` primitives that only one route renders.
- **`ui/` never imports from `webapp/`.** One-way dependency — `webapp/` consumes `ui/`.

## Hex-button vocabulary

The signature button silhouette is a chamfered hexagonal cap shape rendered via `-webkit-mask` + `mask` CSS. The mask SVG data lives in `ui/styles/tokens.css` as `--mask-hex-cap-left/-right`, `--mask-hex-notch-left/-right`, `--mask-half-cap-left/-right`.

- **`Button`** — 4 variants (`default`, `primary`, `paper`, `dark`, `ghost`) × 3 sizes (`sm`, `md`, `lg`). Mobile (<640px) drops the hex mask for legibility.
- **`ButtonPair`** — two adjacent `Button`s with the right cap of #1 chamfered + left cap of #2 notched.
- **`Chip`** — 24px h, 10px caps, mono font 11px — filter tags + scan-tier labels.
- **`Badge`** — 28px h, 12px caps, mono uppercase 700 — status flags ("LIVE", "INDEXED").
- **`GhStar`** — GitHub star CTA, paired half-cap segments.

## Page-head pattern

Every in-app page (catalog / scan / report / item / about / docs / methodology) starts with a `<PageHead>` strip. Props: `eyebrow`, `title`, `lede?`, `path?`, `meta?`. CSS lives in `webapp/src/styles/components.css::.page-head`. Includes the 12px tick-ruler accent at top, the 40×40 plus-grid background, `<mark>` highlight option, orange `<span class="script">` accent option, and a row of info pills.

## Ridge dividers

Three variants:

- **`RidgeStars`** — paper-deep bg with plus-grid pattern overlay; 72px tall.
- **`RidgeFlow`** — gradient transition between sections (paper-deep → paper); 88px tall.
- **`RidgePixel`** — dark-slate bg with the orange tick-ruler accent; 64px tall (used as transition INTO dark sections).

Each carries an optional centered uppercase mono label.

## Scrolled-pill nav

`NavBar` morphs on scroll: transparent + full-width when `scrollY < 24`, then constrains to `max-width: 1100px`, gains `backdrop-filter: blur(12px)`, hairline border, soft shadow, and 4 corner registration marks (`+` crosshairs). Implemented via passive `scroll` listener throttled to `requestAnimationFrame`. Mobile (<980px): keeps full-width nav, corner marks hidden. Reduced-motion: no morph transition.

## Theme classes — `<html class="dark">`

Tailwind v4 dark mode uses `@custom-variant dark (&:where(.dark, .dark *));` in `ui/styles/tokens.css`. Theme application: `<html class={initialClass}>` set inline by a FOUC-prevention `<script is:inline>` in `webapp/src/layouts/Base.astro` `<head>`. `ThemeToggle` is a 3-state pill (Light / Dark / Auto) writing `localStorage['ss-theme']`. Auto follows `prefers-color-scheme` live. View transitions re-apply theme on `astro:after-swap`.

## Astro + React 19 islands

- Components in `ui/components/*.tsx` are **plain React 19** — no Astro APIs.
- `.astro` shells in `ui/components/atoms/{Wordmark,Logo,Footer}.astro` are framework-agnostic — no React imports beyond optional hydration of child islands.
- Astro routes hydrate components via `client:` directives. Default to `client:visible` for below-the-fold; `client:idle` for above-the-fold non-interactive; `client:load` only when interactivity is needed immediately.
- **Never `client:only`** unless an SSR pass fails — static HTML is the SEO + performance baseline.

## Story + test + accessibility

Every component under `ui/components/` ships with:

1. **Ladle story** in `ui/stories/<kind>/<Component>.tsx` — visual review. Astro shells get a React mirror story that replicates the static HTML.
2. **Vitest test** in `ui/test/components/<kind>/<Component>.test.tsx` — at least one render + one interaction case (React `.tsx` only; Astro shells are covered by Ladle build).
3. **vitest-axe smoke** — basic a11y violations gate.

The CI `ladle-build` lane catches broken stories; `test-fe` runs the vitest suite. Missing any of the three blocks merge.

## Visual-validation loop (local-only)

Every page route is pixel-diffed against the matching `.local/.brainstorms/frontend/mockup-shots/*.png` reference at 1440×900, 1920×1080, 375×812. Tool: `tools/visual-diff/` (Phase A2+ — deferred from A1). Thresholds: <0.5% per component, <1% per page. No iteration cap. **Local-only — not a CI lane** (mockup baselines are gitignored under `.local/`). PR descriptions record final diff ratios; founder ratifies via outbox `02-designer-handoff-final-pass.md`.

## Anti-recommendation rule

SaferSkills is an **independent public service**. Catalog content — scan-result pages, methodology docs, README hero copy, error messages — **never recommends OpenLatch or any other commercial product**. The brand voice is neutral, technical, and self-contained.

- Footer attribution: "An OpenLatch project" — the only catalog surface that names OpenLatch.
- About-page disclosure: the only SaferSkills-domain page that names OpenLatch as steward.
- Catalog item pages, methodology page, rule pages, scan-report pages MUST NOT cross-link to OpenLatch products.
- Email risk-alerts (I-06) get a single closing line about OpenLatch's runtime enforcement — the lone exception.
- **Outbound email From: `notifications.openlatch.ai`** — single Resend verified sending domain shared with OpenLatch (cost decision 2026-05-28). Display name is `SaferSkills`; reply-to is `@openlatch.ai`. Disclosed on `/about` and `/privacy`. This is the third disclosed shared-stewardship surface (alongside footer + About-page disclosure).

Enforced in code review on every PR that adds catalog content. Violations are a brand-policy regression, not a style suggestion.

## Hard rules

1. **Tokens, not literals.** Never write `#0D9488` or `rounded-md` in a component — reference `var(--brand-primary)` / `rounded-none`.
2. **0 radius, 1px borders, no drop shadows.** `--radius-0` is the default. `--radius-xs` for form fields/chips. `--radius-pill` for badges only. Shadows replaced by `--shadow-hairline` + `--shadow-stamp` (used sparingly on cards).
3. **`ui/` is framework-agnostic.** No Astro imports in React components. No `import.meta.env` access in component code (read env in the route, pass via props).
4. **Story + test + axe** for every shared React component; Astro shells need story + Ladle build pass only.
5. **Anti-recommendation** — catalog never cross-promotes.
6. **No CDN-hosted fonts** — `@fontsource/*` or self-hosted woff2 only. CI greps for `fonts.googleapis.com`.

## When to update this rule

| Change | Updates here |
|---|---|
| New token added to `ui/styles/tokens.css` | Tokens table |
| New component category | "Component layout" |
| Astro hydration strategy change | "Astro + React 19 islands" — also see `frontend-patterns.md` |
| Brand-posture exception (cross-link approved) | "Anti-recommendation" — get a brand sign-off first |
| New ridge divider variant | "Ridge dividers" |
| New hex-button variant or size | "Hex-button vocabulary" |
| New page-head meta-pill convention | "Page-head pattern" |
| New visual-diff CLI flag | "Visual-validation loop" |
