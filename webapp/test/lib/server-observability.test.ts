import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
  vi.doUnmock('posthog-node')
})

describe('SSR error reporting', () => {
  it('delivers exceptions immediately with service/release tags and deduplicates errors', async () => {
    vi.stubEnv('POSTHOG_PROJECT_KEY', 'phc_test')
    vi.stubEnv('GIT_SHA', 'abc123')
    const capture = vi.fn().mockResolvedValue(undefined)
    const createClient = vi.fn()
    class MockPostHog {
      constructor(...args: unknown[]) {
        createClient(...args)
      }
      captureExceptionImmediate = capture
    }
    vi.doMock('posthog-node', () => ({ PostHog: MockPostHog }))
    const { captureServerException } = await import('@/lib/server-observability')
    const error = new Error('do not export')
    await captureServerException(error, 'api_proxy')
    await captureServerException(error, 'ssr')
    expect(capture).toHaveBeenCalledOnce()
    expect(capture).toHaveBeenCalledWith(
      error,
      'saferskills-webapp-server',
      expect.objectContaining({
        service: 'webapp-server',
        capture_source: 'api_proxy',
        $exception_release: 'abc123',
        $process_person_profile: false,
      })
    )
    expect(createClient).toHaveBeenCalledWith(
      'phc_test',
      expect.objectContaining({
        host: 'https://eu.i.posthog.com',
        requestTimeout: 2000,
        fetchRetryCount: 0,
      })
    )
  })
  it('never replaces application errors when reporting fails', async () => {
    vi.stubEnv('POSTHOG_PROJECT_KEY', 'phc_test')
    vi.doMock('posthog-node', () => ({
      PostHog: class {
        async captureExceptionImmediate() {
          throw new Error('offline')
        }
      },
    }))
    const { captureServerException } = await import('@/lib/server-observability')
    await expect(captureServerException(new Error('original'), 'ssr')).resolves.toBeUndefined()
  })
})
