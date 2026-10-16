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

import { getInitializedPostHog } from '@/lib/observability'

/**
 * Returns whether a feature flag is enabled, falling back to `fallback` when
 * PostHog is unavailable (SSR / not yet initialized / key unset) or the flag is
 * undefined.
 */
export function isFeatureEnabled(flag: string, fallback = false): boolean {
  const client = typeof window === 'undefined' ? undefined : getInitializedPostHog()
  if (!client) return fallback
  try {
    return client.isFeatureEnabled(flag) ?? fallback
  } catch {
    return fallback
  }
}
