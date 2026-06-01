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
| `--shadow-stamp` | `4px 4px 0 0 var(--color-ink)` | Press-block emphasis on **non-interactive** cards + featured items, used sparingly. **Never on buttons** — see Hex-button vocabulary § brutalist offset shadows |
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
│   │                 # ScoreNumber, DotStrip, Eyebrow, Breadcrumb, BracketLabel, Input, PageHead, RidgeStars,
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
│   ├── components.css  # Page-vocabulary CSS (hex masks, page-head, ridges, nav-pill, score language, footer chrome) — ported from mockup
│   └── globals.css   # Tailwind v4 import + tokens + components + @fontsource imports + @layer base + .t-* typography
├── .ladle/           # Ladle story-browser config + global Provider that imports globals.css + Vite Tailwind plugin
└── stories/          # Ladle stories — one per component
webapp/src/components/  # Page-specific compositions (consume ui/)
webapp/src/styles/      # reset.css only (page-vocab CSS lives in ui/styles/components.css now)
```

- **Reusable components → `ui/`.** If a component is used on more than one page, lift it.
- **Page-specific components → `webapp/src/components/`.** Compositions of `ui/` primitives that only one route renders.
- **`ui/` never imports from `webapp/`.** One-way dependency — `webapp/` consumes `ui/`.

### CSS ownership — the one-way rule applies to CSS too

The dependency must be one-way for **stylesheets**, not just imports. A `ui/` component whose CSS physically lives in a `webapp/` page file is an inverted dependency — the component renders unstyled in Ladle (which loads `ui/styles/`, not page CSS) and the page silently owns DS chrome.

- **Any class rendered by a `ui/` component lives in `ui/styles/components.css`** — never in `webapp/src/styles/page-*.css`. (`components.css` is loaded on every page via `global.css → @ui/styles/globals.css → components.css`, and by Ladle — so DS component CSS there renders everywhere, including stories.)
- A **page-specific composition** that only one route renders keeps its CSS in that route's `page-*.css`.
- Decision tree when adding/moving a CSS block:
  - *Rendered by a `ui/` component, or reused across pages?* → `ui/styles/components.css`.
  - *Single-page layout / decorative band / one-off composition?* → that page's `page-*.css`.
- A page **may** override a DS component's appearance for one route (e.g. the homepage's taller `.ridge-pixel`). That override is a legitimate single-page rule and stays in `page-*.css` — it does **not** mean the base CSS belongs there.
- Custom properties consumed by a `ui/` component (e.g. the terminal `--t-*` palette) must be **re-rooted onto the component** in `components.css`, not left scoped to a page ancestor.

### CSS token discipline

Enforced by `scripts/check-css.cjs` (CI `validate` lane + a `repo: local` pre-commit hook):

- **(b) No `var(--token, #hex)` fallback literals** (repo-wide, `ui/styles/**` + `webapp/src/styles/**`). Tokens are always defined in `tokens.css`; a stale hex fallback never renders but lies about the real color and masks dark-mode bugs.
- **(c) No references to undefined custom properties** (repo-wide). Catches typos like the historical `--bg-paper` (→ `--bg-surface`), `--ink` (→ `--color-ink`), `--bg-dotgrid-ink` (→ `--bg-dot-grid`).
- **(a) No bare raw `#rrggbb`** in the cleaned shell page files (`page-catalog` / `page-scan-progress` / `page-scan-report` / `page-scan-submit`) — token-only. `#000`/`#fff` inside `mask`/`url()` compositing are exempt. The ported `page-home.css` (intentional mockup raw-hex) and `components.css` (intentional terminal-ANSI palette) are out of rule (a) scope.

## Hex-button vocabulary

The signature button silhouette is a chamfered hexagonal cap shape rendered via `-webkit-mask` + `mask` CSS. The mask SVG data lives in `ui/styles/tokens.css` as `--mask-hex-cap-left/-right`, `--mask-hex-notch-left/-right`, `--mask-half-cap-left/-right`.

- **`Button`** — 4 variants (`default`, `primary`, `paper`, `dark`, `ghost`) × 3 sizes (`sm`, `md`, `lg`). Mobile (<640px) drops the hex mask for legibility.
- **`ButtonPair`** — two adjacent `Button`s with the right cap of #1 chamfered + left cap of #2 notched.
- **`Chip`** — 24px h, 10px caps, mono font 11px — filter tags + scan-tier labels.
- **`Badge`** — 28px h, 12px caps, mono uppercase 700 — status flags ("LIVE", "INDEXED").
- **`GhStar`** — GitHub star CTA, paired half-cap segments.

### Buttons never use "brutalist" offset shadows

Buttons and any link/control styled as a button (e.g. `.rescan-btn`, `.pkg-gh`) **never** use an offset "stamp"/drop shadow on hover (`box-shadow: 4px 4px 0 …` + `transform: translate(-1px,-1px)`) — that brutalist treatment is banned on interactive controls. Hover state reuses the DS `Button` language: a **background fill** change (e.g. ink→paper, or `primary`→`primary-dark`) plus at most a `translateY(-1px)` lift. No box-shadow, no diagonal nudge.

`--shadow-stamp` is reserved for **non-interactive emphasis on cards/featured items** (e.g. `.rule-card:target`), used sparingly — never on a button. (`--shadow-stamp-brand` was removed; it had no remaining sanctioned use.)

## Page-head pattern

Every in-app page (catalog / scan / report / item / about / docs / methodology) starts with a `<PageHead>` strip. Props: `eyebrow`, `title`, `lede?`, `className?`. CSS lives in `ui/styles/components.css::.page-head`. Includes the 12px tick-ruler accent at top, the 40×40 plus-grid background, `<mark>` highlight option, and an orange `<span class="script">` accent option. The `<mark>` highlight (driven by `--brand-highlight`) is **theme-aware**: pale teal tint on light paper, deep teal (`--ol-brand-primary-dark`) in dark mode — the same treatment as the homepage hero rotator (`--color-citron`), so every highlighted title reads identically across pages and modes.

On every non-homepage page a `<PageRidge>` is placed **directly under** the `<PageHead>` — it provides the header→body transition (replacing the old flat `1px solid ink` border) and carries the page-path cue in its centered label. See "Header ridges" below. (Metadata pills were removed; a future data-heavy page that needs page-level metadata reintroduces a dedicated component then — per scope discipline.)

## Ridge dividers

### Inter-section ridges

Four variants, between content sections:

- **`RidgeStars`** — paper-deep bg with plus-grid pattern overlay; 72px tall.
- **`RidgeFlow`** — gradient transition between sections (paper-deep → paper); 88px tall.
- **`RidgePixel`** — dark-slate bg with the orange tick-ruler accent; 64px tall (used as transition INTO dark sections).
- **`RidgeRuler`** — the quiet one: a 48px paper-deep band carrying only a centered tick ruler (orange majors + faint minors), no fill or hatch. Pure-CSS (no SVG), theme-aware (reads light-on-light and dark-on-dark). A discrete "ruler" seam — e.g. directly under the `/scan` PageHead.

Each carries an optional centered uppercase mono label.

### Header ridges (`PageRidge`)

A separate, taller family (~104–116px) that carries the header→body transition under `<PageHead>`. One distinct `variant` per non-homepage page; all three recombine the same brand cues (contour + plus-grid + wave + tick-ruler) so pages feel unique-but-familiar:

- **`contour`** (`/about`) — topographic contour bundle dissolving toward the content, with a thin tick-ruler edge.
- **`mesh`** (`/methodology`) — a plus-grid field crossed by a dashed alignment seam + scattered teal/orange `+` marks.
- **`swell`** (`/docs`) — a smooth wave bundle with corner registration crosshairs.

Mark colors are token-driven (`--brand-primary` / `--brand-accent` / `--color-ink` via the `.rdg-s-*` classes in `components.css`), so every stroke flips for dark mode for free. Pass `label` for the centered page-path cue (e.g. `label="— /ABOUT —"`). Adding a new page = a new `variant` here + the CSS height/treatment + a Ladle story case.

## Section surfaces

Non-homepage content sections use the shared `.page-section` surface (`ui/styles/components.css`) in an **alternating rhythm**, section to section:

- **`.page-section--grid`** — ruled blueprint grid (60px lines) + a `+` cross at every intersection — the homepage install-band texture, recolored gray-on-light / faint-on-dark.
- **`.page-section--flat`** — a simpler dot grid (26px) on a slightly deeper `--color-paper-deep` band (dark: `--bg-page-alt`).

Both are theme-aware (slate-50 → slate-900 grid, slate-100 → slate-800 flat). The surface owns the section background + vertical padding; page-specific CSS keeps only inner-component typography/layout. **Verify cards on `--flat` bands read correctly in dark mode** — a card whose dark background equals `--bg-page-alt` (slate-800) blends into a flat band; recess it to `--color-paper` (slate-900) or lift it to `--bg-surface-mute` (slate-700). See the `.rule-card` override in `page-methodology.css` for the canonical example.

### Non-homepage page template

`NavBar → PageHead → PageRidge → alternating .page-section bands (with RidgeStars/RidgeFlow between) → CtaBand → Footer`. Every new non-homepage page inherits this template so brand DNA stays consistent.

## Scrolled-pill nav

**`NavBar` is the single top bar — every page mounts `<NavBar>`; never hand-roll another top bar.** The `GhStar` GitHub-star CTA is a **permanent, non-optional** part of NavBar — rendered unconditionally, never gated on the count. `ghCount` is only an SSR placeholder; when a route omits it the chip renders empty and the site-wide `NavStars` island (mounted in `Base.astro`) fills it live. Do **not** reintroduce a `ghCount > 0` guard or otherwise make the GhStar conditional — that was the regression that dropped it from `/items/<slug>` + `/respond`. Covered by `NavBar.test.tsx` ("always renders the GhStar even with no ghCount").

`NavBar` morphs on scroll: transparent + full-width when `scrollY < 24`, then constrains to `max-width: 1100px`, gains `backdrop-filter: blur(12px)`, hairline border, soft shadow, and 4 corner registration marks (`+` crosshairs). Implemented via passive `scroll` listener throttled to `requestAnimationFrame`. Corner marks hidden below 980px. Reduced-motion: no morph transition.

**Mobile collapse (≤860px).** Below 860px — the width at which the horizontal row (wordmark + 5 links + GhStar + scan CTA) no longer fits — the desktop links (`.nav-links`) and right cluster (`.nav-right`) are hidden and a squared, 0-radius, hairline **hamburger button** (`.nav-toggle`) is shown instead. Tapping it opens a slide-down drawer (`.nav-drawer`, absolutely positioned under the bar, `--color-paper` / `--color-line` / `--shadow-hairline`, blurred like the scrolled pill) holding all 5 links + GhStar + the "Scan a repo" CTA stacked. State lives in the `NavBar` island (`useState`); the drawer closes on link click and on `Escape`, carries the `hidden` attribute when closed (so it contributes zero width and stays out of the a11y tree), and its bar-to-X morph sits under the reduced-motion guard. **Active-link state is SSR-correct**: each route passes `activePath={Astro.url.pathname}` to `NavBar` and `aria-current` is derived from that prop — never from `window.location` during render (which caused a hydration mismatch). `≥861px` is byte-for-byte unchanged (`.nav-toggle` / `.nav-drawer` are `display:none`).

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
2. **0 radius, 1px borders, no drop shadows.** `--radius-0` is the default. `--radius-xs` for form fields/chips. `--radius-pill` for badges only. Shadows replaced by `--shadow-hairline` + `--shadow-stamp` (used sparingly on **non-interactive** cards — **never** an offset/brutalist shadow on a button; see Hex-button vocabulary).
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
| New inter-section ridge variant | "Ridge dividers" § Inter-section ridges |
| New `PageRidge` (header ridge) variant | "Ridge dividers" § Header ridges + the new page's `variant` |
| New section-surface class / alternation rule | "Section surfaces" |
| New hex-button variant or size | "Hex-button vocabulary" |
| New visual-diff CLI flag | "Visual-validation loop" |
| New DS-component CSS / relocation | "CSS ownership" — keep the one-way rule (component CSS in `ui/styles/`) |
| New `check-css.cjs` rule / scope change | "CSS token discipline" + `scripts/check-css.cjs` + `ci-cd.md` (validate lane) |
| New runtime-set CSS custom property | `scripts/check-css.cjs` `RUNTIME_VARS` allowlist |
