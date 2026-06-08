/**
 * Astro server middleware — server-side (SSR + `/api/*` proxy) Sentry capture.
 *
 * Closes the previously-dark server error path: SSR page render errors and the
 * `/api/[...path].ts` reverse-proxy. Initializes `@sentry/node` ONCE (module-load
 * guard) reading `process.env.SENTRY_DSN` + `process.env.ENV` at RUNTIME — NOT
 * `PUBLIC_*` (those are build-time/browser). This is the documented server-only
 * env exception, like the existing `API_ORIGIN` proxy (frontend-patterns.md).
 *
 * No-op when `SENTRY_DSN` is unset (dev/test/CI). Errors-only:
 * `sendDefaultPii: false`, `tracesSampleRate: 0`. Shares the capability-token
 * redaction with the browser init (observability.ts) so the unlisted
 * `share_token` never reaches Sentry (security.md § Capability-URL anti-leakage).
 */

import { defineMiddleware } from 'astro:middleware'
import type { ErrorEvent } from '@sentry/node'

import { redactCapabilityToken } from '@/lib/observability'

let sentry: typeof import('@sentry/node') | undefined
let initialized = false

async function ensureSentry(): Promise<typeof import('@sentry/node') | undefined> {
  if (initialized) return sentry
  initialized = true

  const dsn = process.env.SENTRY_DSN
  if (!dsn) return undefined // dev/test/CI — no-op cleanly.

  const Sentry = await import('@sentry/node')
  Sentry.init({
    dsn,
    environment: process.env.ENV ?? 'development',
    sendDefaultPii: false,
    sampleRate: 1.0,
    tracesSampleRate: 0,
    integrations: [],
    beforeBreadcrumb(breadcrumb) {
      // Redact the capability token from any breadcrumb URL (D-UP-32).
      if (typeof breadcrumb.data?.url === 'string') {
        breadcrumb.data.url = redactCapabilityToken(breadcrumb.data.url)
      }
      return breadcrumb
    },
    beforeSend(event: ErrorEvent) {
      // Drop any PII the Node SDK may attach.
      if (event.user) event.user = undefined
      if (event.request?.cookies) event.request.cookies = undefined
      // Never let the unlisted capability token reach Sentry (D-UP-32).
      if (event.request?.url) {
        event.request.url = redactCapabilityToken(event.request.url)
      }
      return event
    },
  })
  sentry = Sentry
  return sentry
}

export const onRequest = defineMiddleware(async (_context, next) => {
  const Sentry = await ensureSentry()
  if (!Sentry) return next()

  try {
    return await next()
  } catch (err) {
    Sentry.captureException(err)
    throw err
  }
})
