/**
 * SaferSkills client-side observability bootstrap.
 *
 * Initialized from Base.astro on `astro:page-load`. Env-checked — both SDKs
 * are no-ops in development when keys are unset. Matches .claude/rules/telemetry.md:
 *   - Sentry: errors only, `sendDefaultPii: false`, breadcrumbs stripped of
 *     any reference to rubric/, schemas/, or user-submitted URLs.
 *   - PostHog: anonymous (no `identify()`); event emission via the closed-enum
 *     allowlist in `webapp/src/lib/analytics.ts`.
 */

let initialized = false

/**
 * Redact the unlisted capability / agent-run token from any `/{scans,agents,
 * agent-scans}/r/<token>` URL so it never reaches Sentry (pairs with the backend
 * access-log + Sentry scrub; security.md § Capability-URL anti-leakage).
 * Possession of the token is full authorization —
 * it must not leak into an error payload. The leading `/` anchors each alternative,
 * so `/agent-scans/r/` never mis-matches the bare `scans` branch.
 */
export function redactCapabilityToken(url: string | undefined): string | undefined {
  if (!url) return url
  return url.replace(/(\/(?:scans|agent-scans|agents)\/r\/)[^/?#]+/g, '$1<redacted>')
}

/**
 * Derive the deployment environment from the runtime hostname (browser-only).
 * Shared by the Sentry `environment` tag and the PostHog `environment`
 * super-property so every event/error is grouped consistently.
 *
 * - hostname contains `staging` OR ends in `.fly.dev` → `staging`
 * - `saferskills.ai` / `www.saferskills.ai` → `production`
 * - anything else (incl. SSR / no `window`) → `development`
 */
export function resolveEnvironment(): 'development' | 'staging' | 'production' {
  if (typeof window === 'undefined') return 'development'
  const host = window.location.hostname
  if (host.includes('staging') || host.endsWith('.fly.dev')) return 'staging'
  if (host === 'saferskills.ai' || host === 'www.saferskills.ai') return 'production'
  return 'development'
}

export async function initObservability(): Promise<void> {
  if (initialized) return
  initialized = true
  await Promise.all([initSentry(), initPostHog()])
}

async function initSentry(): Promise<void> {
  const dsn = import.meta.env.PUBLIC_SENTRY_DSN
  if (!dsn) return

  const Sentry = await import('@sentry/browser')

  Sentry.init({
    dsn,
    environment: resolveEnvironment(),
    release: import.meta.env.PUBLIC_GIT_SHA || undefined,
    sendDefaultPii: false,
    sampleRate: 1.0,
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    integrations: [],
    beforeBreadcrumb(breadcrumb) {
      // Redact the capability token from any breadcrumb URL first.
      if (typeof breadcrumb.data?.url === 'string') {
        breadcrumb.data.url = redactCapabilityToken(breadcrumb.data.url)
      }
      const data = breadcrumb.data
      if (data && typeof data === 'object') {
        const haystack = JSON.stringify(data)
        if (
          haystack.includes('rubric/') ||
          haystack.includes('schemas/') ||
          /https?:\/\//.test(haystack)
        ) {
          return null
        }
      }
      return breadcrumb
    },
    beforeSend(event) {
      if (event.user) {
        event.user = undefined
      }
      if (event.request?.cookies) {
        event.request.cookies = undefined
      }
      // Never let the unlisted capability token reach Sentry.
      if (event.request?.url) {
        event.request.url = redactCapabilityToken(event.request.url)
      }
      return event
    },
  })
}

async function initPostHog(): Promise<void> {
  const key = import.meta.env.PUBLIC_POSTHOG_KEY
  if (!key) return
  const host = import.meta.env.PUBLIC_POSTHOG_HOST ?? 'https://eu.i.posthog.com'

  const { default: posthog } = await import('posthog-js')
  posthog.init(key, {
    api_host: host,
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    disable_session_recording: true,
    persistence: 'memory',
    person_profiles: 'never',
    // `false` enables the /decide call needed for feature flags (feature-flags.ts).
    advanced_disable_decide: false,
    sanitize_properties: (properties) => {
      const sanitized: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(properties)) {
        if (typeof v === 'string' && /https?:\/\//.test(v)) continue
        sanitized[k] = v
      }
      return sanitized
    },
  })
  // Super-properties stamped on EVERY event: the shared-project SaferSkills
  // discriminator (telemetry.md — mandatory) + the env tag.
  posthog.register({ product: 'saferskills', environment: resolveEnvironment() })
}
