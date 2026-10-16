import { PostHog } from 'posthog-node'
import { sanitizeTelemetryProperties } from '@/lib/telemetry-privacy'

let client: PostHog | undefined
const captured = new WeakSet<object>()

function getClient(): PostHog | undefined {
  const key = process.env.POSTHOG_PROJECT_KEY
  if (!key) return
  if (!client) {
    client = new PostHog(key, {
      host: 'https://eu.i.posthog.com',
      disableGeoip: true,
      flushAt: 1,
      requestTimeout: 2000,
      fetchRetryCount: 0,
      before_send: (event) => {
        const properties = sanitizeTelemetryProperties(event.properties)
        return properties ? { ...event, properties } : null
      },
    })
  }
  return client
}

export async function captureServerException(
  error: unknown,
  source: 'ssr' | 'api_proxy'
): Promise<void> {
  try {
    const posthog = getClient()
    if (!posthog) return
    if (error && typeof error === 'object') {
      if (captured.has(error)) return
      captured.add(error)
    }
    // Immediate delivery is bounded by requestTimeout; no pending queue at process exit.
    await posthog.captureExceptionImmediate(error, 'saferskills-webapp-server', {
      product: 'saferskills',
      environment: process.env.ENV || 'development',
      service: 'webapp-server',
      release: process.env.GIT_SHA || 'development',
      capture_source: source,
      $exception_release: process.env.GIT_SHA || 'development',
      $process_person_profile: false,
    })
  } catch {
    // Reporting must not replace the original error or break proxy responses.
  }
}
