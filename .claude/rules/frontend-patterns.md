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
├── methodology.astro      → /methodology
└── appeal.astro           → /appeal       (W6)
```

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
