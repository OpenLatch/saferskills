---
paths:
  - "webapp/**"
  - "ui/**"
---

# Frontend Patterns

> **Paths**: `webapp/**`, `ui/**`

## Routing — Astro file-based

Routes live under `webapp/src/pages/` as `.astro` files. The path on disk maps directly to the URL:

```
webapp/src/pages/
├── index.astro            → /
├── catalog/index.astro    → /catalog
├── catalog/[id].astro     → /catalog/:id
├── scans/[id].astro       → /scans/:id          (public run report; 404s unlisted runs)
├── scans/r/[token].astro  → /scans/r/:token     (unlisted capability URL — SSR, noindex, no-store)
├── methodology.astro      → /methodology
└── appeal.astro           → /appeal       (W6)
```

The unlisted capability-URL page (`scans/r/[token].astro`) sets all three anti-leakage headers at the **page** level (`Referrer-Policy: no-referrer`, `Cache-Control: private, no-store`, `X-Robots-Tag: noindex, nofollow`) + `Base noindex` (which also suppresses the token-bearing `canonical`/`og:url`). It reuses the same report body as `/scans/:id` via the shared `components/scan/ScanRunReport.astro`, which branches three ways: **single-cap upload** → rich score/source layout (mockups 3/4); **multi-file upload** → the same rich body per file behind a `FileTabStrip` (one tab per fanned-out capability, I-3.5); **repo scan** → the multi-capability cap-list table (`ScanReportView`, mockups 5/6). All uploads (1 or N) render via `components/scan/UploadReport.tsx`; the `isUpload` branch decides upload-vs-repo (not `isRich`, which now only gates the page-head). Unlisted runs add the private banner + `UnlistedManageBar` + `ExpiryCountdown`. The "Share this result" badge band is the shared `ShareResultBand.tsx` (React, reused by the repo path **and** per-file in `UploadReport`). See `.claude/rules/security.md` § Capability-URL anti-leakage.

- **No client-side router.** Astro handles every route as a server render → HTML → React island hydration.
- **Astro `output: 'server'`** (`@astrojs/node` standalone adapter; per-page `export const prerender = true` opts INTO SSG). Marketing pages stay statically prerendered at build time; dynamic surfaces (catalog with URL filters, `/scans/[id]`, `/items/[slug]`, badge/OG endpoints) stay SSR.
- **Dynamic segments** use `[param].astro` (single) or `[...slug].astro` (catch-all).
- **Layouts** live in `webapp/src/layouts/` and are imported per page; never hidden via global config.

## React 19 islands

Astro pages mount React components as islands using `client:` directives:

| Directive | Use when |
|---|---|
| `client:idle` | Above-the-fold component that needs JS but not immediately interactive |
| `client:load` | Above-the-fold component that needs JS at first paint (rare) |
| `client:visible` | Below-the-fold component (most cases) |
| `client:only="react"` | **Avoid.** Only when SSR genuinely fails (e.g. component reads `window` during render). Static HTML is the SEO + performance baseline. |

Components are framework-agnostic React 19 (cf. `design-system.md` — `ui/` never imports Astro APIs). Pass data via props from the `.astro` route, never via Astro-specific context.

## State management

| Need | Tool |
|---|---|
| Local component state | `useState` / `useReducer` |
| Cross-component state inside a single island | `useReducer` + React context |
| Cross-island state | Zustand store under `webapp/src/stores/` |
| Server data (when auth lands W5) | TanStack Query |
| Form state | `react-hook-form` + Zod resolver |

**At W1 there is no TanStack Query.** API reads happen via `fetch()` against `env.PUBLIC_API_URL`, with response shapes typed by the generated DTOs at `webapp/src/generated/openapi/types.gen.ts`. The Query layer arrives with auth.

## Data fetching pattern (W1)

```ts
// webapp/src/lib/api.ts
import { env } from '@/env';
import type { ArtifactList } from '@/generated/openapi/types.gen';

export async function listArtifacts(): Promise<ArtifactList> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/artifacts`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}
```

- Always type the return via the generated DTO. Never `as` cast away the generated type — if a route returns an undocumented shape, fix the backend response_model first.
- Fetch errors throw; the React island's error boundary catches.
- Server-rendered pages can call the same `lib/api.ts` functions from Astro's frontmatter — `fetch` is universal in Astro.

## Form validation — Zod

- Form schemas import from `webapp/src/generated/zod/` when the backend already defines the entity (`AppealCreate`, `RescanRequest`).
- Hand-written form schemas (e.g. a transient UI state object) live under `webapp/src/lib/forms/`.
- `react-hook-form` wires the Zod schema via `@hookform/resolvers/zod`.

## SSE pattern — `useScanProgress`

Long-running scan progress is streamed from the backend via Server-Sent Events on `GET /api/v1/scans/<id>/events` (cf. D-FE-09 + D-FE-34 in `INDEX.md`). The frontend hook `webapp/src/lib/hooks/useScanProgress.ts` is the canonical pattern:

- Opens an `EventSource` against `${env.PUBLIC_API_URL}/api/v1/scans/<id>/events`.
- Parses `progress` event frames and reduces them into a `ScanProgressState` via `useReducer`.
- **Reconnect strategy**: exponential backoff 1s → 2s → 4s (max 3 attempts) on `onerror`.
- **Polling fallback**: after 3 failed reconnects, falls back to `fetchScanById` every 1.5s until the scan reaches a terminal state.
- **Resume semantics**: each SSE frame carries `id: <scan_id>-<event_seq>`; on reconnect the browser sends `Last-Event-ID` and the backend replays from `scan_events` rows past that sequence.
- **Cleanup**: the effect's cleanup closes the `EventSource` and clears the polling timer.

Use the hook from React islands hydrated with `client:load` (the progress board needs to be live immediately when the user lands on `/scans/<id>`). Reduced-motion is handled at the molecule level (e.g. `ScanProgressBar`'s `reducedMotion` prop), not the hook.

## Live data on a prerendered page (fallback primitives)

**No metric is primarily hardcoded.** Every displayed data value originates from a live API call; an impressive launch placeholder survives ONLY as a fallback when the live source is too thin to look good. This keeps a page beautiful with an empty catalog and silently switches to real data as it fills.

The primitives live in `webapp/src/lib/fallback.ts`:

- `pickList(live, placeholder, minItems = 3)` — use the live array only when it has ≥ `minItems` items.
- `pickCount(live, placeholder, minCount = 10)` — use the live scalar only when it clears the floor. (`rule_count` passes `minCount = 1` — any rule count is meaningful.)
- `fetchOrNull(fn)` — error-safe fetch → `null`, so the picker (not a scattered `.catch(() => [])`) decides live-vs-placeholder.

Fallback values are quarantined in **one** clearly-labeled module (`webapp/src/data/launch-fallbacks.ts`), header-commented "Used ONLY as fallback — never a primary source." Genuine config/copy/cited-facts (install paths, curated marketing taxonomy, scoring weights, About-page cited stats) stays out of it.

### Build-seed-then-island-refresh

The canonical shape for a **prerendered** page (`export const prerender = true`) that must stay fresh:

1. A single view-model function (e.g. `lib/homepage.ts::getHomepageData`) fetches every source in parallel via `fetchOrNull`, runs the pickers, and returns one fully-resolved object.
2. The `.astro` frontmatter calls it at **build time** and renders real-or-placeholder values into the static HTML — correct even with an empty catalog and JS disabled (Lighthouse ≥90 preserved).
3. A small **island** (`client:idle`) seeded with the build-time view-model re-runs the same function on the client and **patches the existing SSR DOM in place** — it renders `null`, never rewrites structure. Scalar nodes carry `data-live-stat="<key>"`; list cells (feed cards) carry a stable `data-live-card`/container hook. Build with `textContent` + DOM nodes, **never `innerHTML` with API-derived strings** (anonymous-submitted GitHub URLs flow into `author`/`slug`).

Counts derived from a config array (e.g. `SUPPORTED_AGENTS.length`) are config-derived, not magic literals — fine. The rule is **no orphan metric literals**. A build-time count that needs no API (e.g. "N detection rules") reads from generated data: `import { ruleCount } from '@/generated/methodology/index.mdx'`.

## Tailwind v4

- **No `tailwind.config.js`.** Tokens live in `ui/styles/tokens.css` via the `@theme` directive (cf. `design-system.md`).
- **Integration is `@tailwindcss/vite`** registered in `webapp/astro.config.mjs::vite.plugins`. The legacy `@astrojs/tailwind` integration is NOT used.
- The `@import "tailwindcss"` entrypoint lives in `ui/styles/globals.css`; webapp imports it transitively via `webapp/src/styles/global.css`.
- **Dark mode** uses `@custom-variant dark (&:where(.dark, .dark *));`. Apply `<html class="dark">` (FOUC-prevention script in `Base.astro` handles initial state) — never `data-theme` or descendant variants.
- Class names use Tailwind primitives + token-aliased custom utilities (e.g. `bg-brand-primary`, `text-fg-1`, `border-line`, `rounded-none`).
- **No `@apply` in feature code** — keep utility classes in JSX. `@apply` is allowed only in `ui/styles/globals.css` for resets.

## Component composition

- **`ui/`** = primitives + shared compositions. Reusable across pages.
- **`webapp/src/components/`** = page-specific compositions. One route, one component tree.
- **`webapp/src/pages/`** = thin Astro routes that wire `webapp/src/components/` islands together.

If a `webapp/src/components/` piece grows reusable, lift it to `ui/` — own one Ladle story + vitest test + axe smoke (cf. `design-system.md`).

## Hard rules

1. **No `client:only`** unless SSR genuinely fails for that component.
2. **Generated DTOs are the source of truth** — `as` casts that fight a generated type are a regression in the schema, not the frontend.
3. **No direct `import.meta.env`** in feature code — always via `webapp/src/env.ts` (cf. `environment-config.md`).
4. **Tailwind v4 tokens**, never hex literals — see `design-system.md`.
5. **Forms use Zod** + `react-hook-form` — never hand-rolled validation in JSX.

## When to update this rule

| Change | Updates here |
|---|---|
| New route under `webapp/src/pages/` | "Routing" map |
| New `client:` strategy adopted | "React 19 islands" table |
| TanStack Query arrives (auth lands W5) | "State management" + "Data fetching pattern" |
| New store under `webapp/src/stores/` | "State management" |
| New form schema location | "Form validation" |
