<div align="center">

<a href="../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>Design system</h3>
<p>Framework-agnostic React 19 + Tailwind v4 components and the brand tokens.</p>

</div>

## What it is

`@saferskills/ui` is the shared design system — the single source of the brand tokens plus the framework-agnostic React 19 + Tailwind v4 atoms, molecules, and thin Astro shells every SaferSkills surface is built from. It is consumed by [`webapp/`](../webapp/README.md); the dependency is one-way (`ui/` never imports from `webapp/`).

The brand sits on an emerald-teal palette (`#0D9488`) with a distinct shape language — chamfered hex-cap buttons, page-head + ridge dividers — and type stack (DM Sans / Space Mono / Anybody / Nanum Pen Script + the Onest 600 wordmark). 0px radius, 1px hairlines, no drop shadows.

## Layout

```
ui/
├── components/
│   ├── atoms/        # Button, Chip, Badge, Wordmark, ScoreNumber, PageHead, ridges, …
│   ├── molecules/    # NavBar, CtaBand, FindingDetail, DropZone, score/report blocks, …
│   └── organisms/    # composition shells
├── styles/
│   ├── tokens.css      # the token SSOT (color, type, spacing, score bands) + Tailwind @theme
│   ├── components.css  # DS-component CSS (hex masks, page-head, ridges, score language)
│   └── globals.css     # Tailwind import + tokens + components + fonts
├── .ladle/           # Ladle story-browser config
└── stories/          # one story per component
```

## Develop

```bash
pnpm test                 # Vitest + vitest-axe
pnpm ladle:dev            # http://localhost:61000 — story browser
pnpm ladle:build          # static export — gated in CI on PRs touching ui/
```

## Conventions

- **Tokens are the single source of truth.** Components never hardcode color / radius / spacing — reference `var(--…)` or the Tailwind `@theme` utilities. No magic numbers.
- **Every shared React component ships a Ladle story + a Vitest test + a vitest-axe smoke.** Astro shells ship a Ladle mirror story + build pass. Missing any one blocks merge.
- **CSS ownership is one-way.** Any class a `ui/` component renders lives in `ui/styles/components.css`, never in a `webapp/` page file.
- **Anti-recommendation.** Catalog content never cross-recommends OpenLatch; the footer "An OpenLatch project" attribution is the only permitted mention.

Full contract: [`.claude/rules/design-system.md`](../.claude/rules/design-system.md) and [`ui/CLAUDE.md`](./CLAUDE.md).

---

<sub>Part of **[SaferSkills](../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
