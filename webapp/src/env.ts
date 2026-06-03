import { z } from 'zod'

/**
 * Resolve the API base URL by execution context.
 *
 * - **Browser** → the page's own origin. The webapp reverse-proxies same-origin
 *   `/api/*` calls to the backend (`webapp/src/pages/api/[...path].ts`), so the
 *   client never needs a cross-origin (CORS) URL and the value is correct on
 *   every host. This is what makes one build valid for staging AND prod
 *   (build-once / deploy-many) — no per-env build-arg, no `localhost` baked in.
 * - **Server (SSR + prerender build)** → `API_ORIGIN`, a runtime, server-only
 *   var (NOT `PUBLIC_*`, never inlined into the client bundle) set per Fly app.
 *   Frontmatter/build fetches talk to the backend directly. Falls back to
 *   localhost for local `pnpm dev` / `pnpm build`.
 *
 * Returns an absolute origin in both contexts so existing `new URL(base+path)`
 * call-sites keep working unchanged. See `.claude/rules/frontend-patterns.md`
 * § Data fetching and `.claude/rules/environment-config.md`.
 */
function resolveApiBase(): string {
  if (typeof window !== 'undefined') return window.location.origin
  const serverOrigin = typeof process !== 'undefined' ? process.env.API_ORIGIN : undefined
  return serverOrigin ?? 'http://localhost:8000'
}

const envSchema = z.object({
  PUBLIC_API_URL: z.string().url().default('http://localhost:8000'),
  PUBLIC_POSTHOG_KEY: z.string().optional(),
  PUBLIC_POSTHOG_HOST: z.string().url().default('https://eu.posthog.com'),
  PUBLIC_SENTRY_DSN: z.string().optional(),
  PUBLIC_TURNSTILE_SITE_KEY: z.string().optional(),
})

export const env = envSchema.parse({
  // Resolved at runtime per context (browser origin vs server API_ORIGIN) — NOT
  // the build-time `import.meta.env.PUBLIC_API_URL`, which would freeze one host
  // into the shared image. The other PUBLIC_* values are genuinely env-identical
  // across staging+prod, so they stay build-time inlined.
  PUBLIC_API_URL: resolveApiBase(),
  PUBLIC_POSTHOG_KEY: import.meta.env.PUBLIC_POSTHOG_KEY,
  PUBLIC_POSTHOG_HOST: import.meta.env.PUBLIC_POSTHOG_HOST,
  PUBLIC_SENTRY_DSN: import.meta.env.PUBLIC_SENTRY_DSN,
  PUBLIC_TURNSTILE_SITE_KEY: import.meta.env.PUBLIC_TURNSTILE_SITE_KEY,
})

export type Env = z.infer<typeof envSchema>
