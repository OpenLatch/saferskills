/** Anonymous browser analytics and exception capture for the SaferSkills EU project. */
import { sanitizeTelemetryProperties } from '@/lib/telemetry-privacy'

let initialization: Promise<void> | undefined
let browserClient: typeof import('posthog-js').default | undefined
let handlersInstalled = false
const captured = new WeakSet<object>()

export function resolveEnvironment(): 'development' | 'staging' | 'production' {
  if (typeof window === 'undefined') return 'development'
  const host = window.location.hostname
  if (host.includes('staging') || host.endsWith('.fly.dev')) return 'staging'
  if (host === 'saferskills.ai' || host === 'www.saferskills.ai') return 'production'
  return 'development'
}

export async function captureBrowserException(error: unknown): Promise<void> {
  try {
    if (!import.meta.env.PUBLIC_POSTHOG_KEY) return
    await initObservability()
    if (error && typeof error === 'object') {
      if (captured.has(error)) return
      captured.add(error)
    }
    browserClient?.captureException(error)
  } catch {
    // Diagnostics must never create a second application error.
  }
}

export function initObservability(): Promise<void> {
  if (!import.meta.env.PUBLIC_POSTHOG_KEY) return Promise.resolve()
  if (!initialization) {
    initialization = initialize(import.meta.env.PUBLIC_POSTHOG_KEY).catch((error: unknown) => {
      initialization = undefined
      throw error
    })
  }
  return initialization
}

async function initialize(projectKey: string): Promise<void> {
  const { default: posthog } = await import('posthog-js')
  posthog.init(projectKey, {
    api_host: '/ingest',
    ui_host: 'https://eu.posthog.com',
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    capture_exceptions: false,
    disable_session_recording: true,
    disable_surveys: true,
    persistence: 'memory',
    save_referrer: false,
    save_campaign_params: false,
    person_profiles: 'never',
    advanced_disable_decide: false,
    before_send: (event) => {
      if (!event) return null
      const properties = sanitizeTelemetryProperties(event.properties)
      return properties ? { ...event, properties } : null
    },
  })
  posthog.register({
    product: 'saferskills',
    environment: resolveEnvironment(),
    service: 'webapp-browser',
    release: import.meta.env.PUBLIC_GIT_SHA || 'development',
    $exception_release: import.meta.env.PUBLIC_GIT_SHA || 'development',
  })
  browserClient = posthog
}

export function getInitializedPostHog(): typeof browserClient {
  return browserClient
}

/** Install synchronously before the idle SDK import; React 19 also reports here. */
export function installErrorHandlers(): void {
  if (handlersInstalled) return
  handlersInstalled = true
  window.addEventListener('error', (event) => {
    if (event.error) void captureBrowserException(event.error)
  })
  window.addEventListener('unhandledrejection', (event) => {
    void captureBrowserException(event.reason)
  })
}
