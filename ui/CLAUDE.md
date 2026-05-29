# CLAUDE.md — ui/

Shared design system: tokens + framework-agnostic React 19 atoms + thin Astro shells. Brand sits on the OpenLatch-shared teal palette with distinction-by-shape (hex caps + page-head + ridge dividers + header ridges + alternating section surfaces) and distinction-by-type (DM Sans / Space Mono / Anybody / Nanum Pen Script + Onest 600 wordmark).

Non-homepage pages follow a fixed template — `NavBar → PageHead → PageRidge → alternating .page-section bands → CtaBand → Footer`. `PageRidge` (`contour` / `mesh` / `swell`) is the rich header→body divider under `PageHead`; `.page-section--grid` / `.page-section--flat` (in `styles/components.css`) are the canonical alternating section surfaces. See `.claude/rules/design-system.md` § Header ridges + § Section surfaces.

## Hard rules

1. **`styles/tokens.css` is the only color / typography / spacing source.** No magic numbers in components.
2. **Atoms are React 19 + Tailwind primitives.** Never import Astro APIs from `.tsx` components. Astro-only thin shells (`Wordmark.astro`, `Logo.astro`, `Footer.astro`, `RecentScanCard.astro`, `TrendScanCard.astro`) are framework-agnostic — no React imports beyond optional child-island hydration.
3. **0 radius, 1px hairlines, no drop shadows.** `--radius-0` is the default; `--radius-xs` (2px) for form fields + chips; `--radius-pill` (999px) for badges only. Shadows replaced by `--shadow-hairline` (1px ink ring) + `--shadow-stamp` (4px offset block press shadow on cards, sparingly).
4. **Anti-recommendation.** No OpenLatch cross-recommendation in catalog content. Footer attribution ("An OpenLatch project") is the single permitted mention.
5. **Every shared React component ships with: Ladle story + vitest render test + vitest-axe smoke.** Astro shells ship a Ladle React mirror story + Ladle build pass (no vitest; jsdom can't render `.astro` directly).
6. **`<html class="dark">` is the dark-mode signal.** Components read `:where(.dark, .dark *)` via Tailwind v4's `@custom-variant dark`. Never compose a separate light/dark stylesheet.

See `.claude/rules/design-system.md` for the full contract.
