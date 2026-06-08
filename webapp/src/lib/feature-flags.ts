/**
 * Minimal feature-flag reader over the already-initialized `posthog-js` client.
 *
 * PostHog is bootstrapped in `webapp/src/lib/observability.ts` (on idle from
 * Base.astro). This module never initializes it — it only reads flags off the
 * live client. It is a safe no-op (returns `fallback`) in SSR, before the client
 * is initialized, or when the key is unset, so callers never need a guard.
 *
 * Flag names are a CLOSED, REVIEWED set (mirrors the closed-enum event discipline
 * in telemetry.md). Adding a flag is a reviewed change here — never an arbitrary
 * string at the call-site. Example flag name (not actually gating anything yet):
 *   - `saferskills-example-flag`
 */

import type posthog from 'posthog-js'

type PostHogGlobal = typeof posthog

/**
 * Read the already-initialized posthog singleton off `window` without importing
 * (and thus without ever bundling/forcing init from this module). `posthog.init`
 * (observability.ts) exposes the live singleton as `window.posthog`. We treat a
 * client with no `__loaded` flag as not-yet-initialized → `fallback`.
 */
function getClient(): PostHogGlobal | undefined {
  if (typeof window === 'undefined') return undefined
  const client = (window as Window & { posthog?: PostHogGlobal }).posthog
  if (!client || (client as unknown as { __loaded?: boolean }).__loaded !== true) {
    return undefined
  }
  return client
}

/**
 * Returns whether a feature flag is enabled, falling back to `fallback` when
 * PostHog is unavailable (SSR / not yet initialized / key unset) or the flag is
 * undefined.
 */
export function isFeatureEnabled(flag: string, fallback = false): boolean {
  const client = getClient()
  if (!client) return fallback
  try {
    return client.isFeatureEnabled(flag) ?? fallback
  } catch {
    return fallback
  }
}
