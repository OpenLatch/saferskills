/**
 * SaferSkills client-side observability bootstrap.
 *
 * Initialized from Base.astro on `astro:page-load`. Env-checked — both SDKs
 * are no-ops in development when keys are unset. Matches .claude/rules/telemetry.md:
 *   - Sentry: errors only, `sendDefaultPii: false`, breadcrumbs stripped of
 *     any reference to rubric/, schemas/, or user-submitted URLs.
 *   - PostHog: anonymous (no `identify()`); event emission via the closed-enum
 *     allowlist in `webapp/src/lib/analytics.ts` (lands with Phase A2 pages).
 */

let initialized = false

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
    sendDefaultPii: false,
    sampleRate: 1.0,
    tracesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    integrations: [],
    beforeBreadcrumb(breadcrumb) {
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
      return event
    },
  })
}

async function initPostHog(): Promise<void> {
  const key = import.meta.env.PUBLIC_POSTHOG_KEY
  if (!key) return
  const host = import.meta.env.PUBLIC_POSTHOG_HOST ?? 'https://eu.posthog.com'

  const { default: posthog } = await import('posthog-js')
  posthog.init(key, {
    api_host: host,
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    disable_session_recording: true,
    persistence: 'memory',
    person_profiles: 'never',
    advanced_disable_decide: true,
    sanitize_properties: (properties) => {
      const sanitized: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(properties)) {
        if (typeof v === 'string' && /https?:\/\//.test(v)) continue
        sanitized[k] = v
      }
      return sanitized
    },
  })
}
