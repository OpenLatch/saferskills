<div align="center">

<a href="../README.md">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../webapp/public/logos/saferskills-dark-wordmark.svg">
    <img alt="SaferSkills" src="../webapp/public/logos/saferskills-light-wordmark.svg" height="38">
  </picture>
</a>

<h3>Public website</h3>
<p>The Astro 6 + React 19 catalog, scan reports, and docs at saferskills.ai.</p>

</div>

## What it is

The public SaferSkills website — the catalog, scan + agent reports, the native docs, and the marketing surfaces at [saferskills.ai](https://saferskills.ai). Astro 6 (`output: 'server'`, with per-page `prerender`) + React 19 islands + Tailwind v4 via `@tailwindcss/vite`. It consumes the [`ui/`](../ui/README.md) design system and reaches the [API](../services/api/README.md) same-origin through an in-app `/api/*` reverse proxy — no CORS, no API URL baked into the bundle.

## Run locally

```bash
cd webapp
pnpm install
pnpm dev               # http://localhost:5173
```

`pnpm dev` expects the API reachable at `API_ORIGIN` (default `http://localhost:8000`); the simplest full stack is `docker compose up` from the repo root.

## Build & test

```bash
pnpm build             # SSR build → dist/server/entry.mjs
pnpm preview           # serve the built bundle
pnpm test              # Vitest unit + axe smoke
```

The container runs `node ./dist/server/entry.mjs`.

## Layout

```
src/
├── pages/            # Astro routes (file-based) — home, capabilities, scan,
│   │                 # scans/[id], agents/[id], items/[slug], methodology, docs/**,
│   │                 # badge + OG endpoints, api/[...path].ts (same-origin API proxy)
│   └── ...
├── components/       # page-specific React/Astro compositions (consume ui/)
├── content/docs/**   # the native I-06 docs (markdown/MDX → /docs/*)
├── layouts/          # Base.astro (HTML shell, fonts, theme, OG/meta) + DocsLayout
├── styles/           # global.css (imports @ui/styles) + reset + page-*.css shells
├── lib/              # api client, hooks (useScanProgress, useUploadFlow), fallbacks
└── generated/        # ← codegen output (never hand-edit): openapi types + Zod
public/               # logos, favicons, PWA manifest, OG image
```

## See also

- [`webapp/CLAUDE.md`](./CLAUDE.md) — hard rules (SSG opt-in, theme, aliases, API proxy)
- [`.claude/rules/frontend-patterns.md`](../.claude/rules/frontend-patterns.md) — routing, islands, data fetching
- [`.claude/rules/design-system.md`](../.claude/rules/design-system.md) — tokens + components
- [`../ui/README.md`](../ui/README.md) — the design system it consumes

---

<sub>Part of **[SaferSkills](../README.md)** — every AI capability, independently scanned. · An [OpenLatch](https://openlatch.ai) project · [saferskills.ai](https://saferskills.ai)</sub>
