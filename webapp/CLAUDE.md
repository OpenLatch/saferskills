# CLAUDE.md — webapp/

SaferSkills public website. Astro 6 (output: server) + React 19 islands + Tailwind v4 via the `@tailwindcss/vite` plugin.

## Hard rules

1. **Routes opt INTO SSG.** `astro.config.mjs` sets `output: 'server'` with the `@astrojs/node` adapter. Static pages add `export const prerender = true` at the top of their frontmatter (homepage, about, methodology, /docs, /404). Dynamic pages stay SSR — catalog (URL-driven filters), `/scans/[id]`, `/items/[slug]`, badge/OG endpoints, and the `/api/[...path].ts` same-origin reverse proxy (forwards `/api/*` to the runtime `API_ORIGIN` backend; see `.claude/rules/frontend-patterns.md` § Same-origin API proxy).
2. **Style entry is `webapp/src/styles/global.css`.** That file `@import`s `@ui/styles/globals.css` (Tailwind + tokens + page-vocabulary CSS + fonts + typography utilities) → `./reset.css` (webapp-specific base resets). The page-vocabulary CSS (`.btn`, `.chip`, `.page-head`, `.ridge-*`, etc.) lives in `ui/styles/components.css` so Ladle stories render with the same chrome the webapp ships.
3. **No CDN fonts.** All fonts via `@fontsource/*` or `@fontsource-variable/*`. The `validate` CI lane fails on any `fonts.googleapis.com` in committed source.
4. **Layouts set `<html lang="en">`** (no className). The FOUC-prevention inline script in `Base.astro` flips `<html class="dark">` based on `localStorage['ss-theme']` + `prefers-color-scheme` BEFORE first paint. `ThemeToggle` (a React 19 island) writes the same key.
5. **Observability lives in `webapp/src/lib/observability.ts`.** Sentry + PostHog SDKs init only when `PUBLIC_SENTRY_DSN` / `PUBLIC_POSTHOG_KEY` are set. Init runs on `requestIdleCallback` from `Base.astro` so it never blocks first paint.
6. **`@/*` resolves to `webapp/src/*`.** `@ui/*` resolves to `ui/*`. Use these aliases — never relative `../../../` paths into `ui/`.

## Pages

- `index.astro` — homepage
- `methodology.astro` — auto-generated rule index
- `privacy.astro`, `terms.astro` — legal pages
- `about.astro`, `docs/index.astro`, `404.astro`
- `capabilities/index.astro` — the browse surface (renamed from `/catalog`; `catalog/index.astro` is now a thin 301 redirect that preserves the query string), plus `scan/index.astro` and `scans/[id].astro`
- `items/[slug].astro`, `items/[slug]/respond.astro`, `badge/[scan_id]/[score].svg.ts`, `og/{scan,item}/[id].png.ts`

The Agent Report: `agents/[id].astro` (public) + `agents/r/[token].astro` (unlisted, noindex/no-store/no-referrer). Both SSR (`prerender=false`), mirror the `/scans` pair, and render the shared island `components/agent/AgentReport.tsx`. The page is `/agents/*`; the API stays `/api/v1/agent-scans/*`. See `.claude/rules/frontend-patterns.md` § Routing.

`scan/index.astro` is the umbrella scan page — the `[01 Capability | 02 Agent]` mode control lives in ONE island (`components/scan/ScanModeShell.tsx`), `?mode=agent` is SSR-respected — alongside `agents/scan.astro` (the prerendered platform-picker activation page, `PageRidge variant="circuit"`; the static segment beats `/agents/[id]`). Both render the shared `components/scan/AgentScanActivation.tsx` island. See `.claude/rules/frontend-patterns.md` § Routing.

`slack.astro` → `/slack` (SSR, `prerender=false`) is the stable, shareable community-Slack URL: it 302s through the same-origin `/api/*` proxy to `GET /api/v1/community/slack/redirect`, which holds the live invite. Backs the NavBar `SlackHexButton` + the footer "Join Slack Community" link.

## Brand-asset assets

- `public/logos/` — 9 SVG variants of the locked S-monogram + wordmark. Source for inline use.
- `public/favicon.svg`, `public/favicon-{16,32,48}.png`, `public/favicon.ico`, `public/apple-touch-icon.png`, `public/icon-{192,512}.png`, `public/icon-maskable-512.png`, `public/og-image.png`, `public/site.webmanifest` — full PWA + favicon suite. Manifest theme colors track the brand (`#0D9488` light, `#0F766E` dark).

## Local dev

```bash
pnpm dev                    # astro dev on :5173
pnpm build                  # SSR build → dist/server/entry.mjs
pnpm preview                # serve the built bundle
pnpm test                   # vitest
```

Docker:

```bash
docker compose up           # postgres + api + webapp (Node 24 alpine, :5173)
```

The webapp container runs `node ./dist/server/entry.mjs` per the `webapp/Dockerfile` (the earlier nginx static host is gone).
