import { afterEach, describe, expect, it, vi } from 'vitest'
import { sanitizeTelemetryProperties } from '@/lib/telemetry-privacy'

const TOKEN = 'Hh3y6Qk2pN8fT0aZ1cV9bWx'
const BUNDLE = 'https://saferskills.ai/_astro/Scan.abcd1234.js'

describe('telemetry privacy boundary', () => {
  it('preserves closed numeric buckets and the public ingestion key', () => {
    expect(
      sanitizeTelemetryProperties({ token: 'phc_test', query_length_bucket: '>=50' })
    ).toMatchObject({ token: 'phc_test', query_length_bucket: '>=50' })
  })
  it('removes nested capability tokens, messages, source excerpts, and arbitrary context', () => {
    const clean = sanitizeTelemetryProperties({
      product: 'saferskills',
      kind: 'skill',
      $current_url: `https://saferskills.ai/scans/r/${TOKEN}`,
      $referrer: 'https://private.example/secret',
      headers: { authorization: TOKEN },
      custom: { input: 'secret source' },
      $exception_list: [
        {
          type: 'TypeError',
          value: TOKEN,
          stacktrace: {
            frames: [
              {
                filename: BUNDLE,
                lineno: 42,
                colno: 7,
                function: 'submitScan',
                context_line: TOKEN,
              },
              { filename: `/upload/${TOKEN}/private.txt`, lineno: 2 },
            ],
          },
          cause: { value: TOKEN },
        },
      ],
    })
    expect(JSON.stringify(clean)).not.toContain(TOKEN)
    expect(JSON.stringify(clean)).not.toContain('private')
    expect(clean?.kind).toBe('skill')
    expect(clean?.$exception_list).toEqual([
      {
        type: 'TypeError',
        value: '[redacted]',
        stacktrace: {
          type: 'raw',
          frames: [
            {
              filename: BUNDLE,
              platform: 'web:javascript',
              lineno: 42,
              colno: 7,
              function: 'submitScan',
            },
          ],
        },
      },
    ])
  })
  it('retains only deployed bundle locations and injected source-map identities', () => {
    const clean = sanitizeTelemetryProperties({
      $release_id: 'ab123',
      $exception_list: [
        {
          type: 'TokenFromUser',
          stacktrace: {
            frames: [
              {
                filename: '/app/dist/server/chunks/entry_abc.mjs',
                chunk_id: '12345678-1234-1234-1234-123456789abc',
              },
              { filename: `${BUNDLE}?token=${TOKEN}` },
              { filename: 'https://evil.test/_astro/entry.js' },
              { filename: '/app/dist/server/../../uploads/private.js' },
            ],
          },
        },
      ],
    })
    expect(clean?.$release_id).toBe('ab123')
    expect(JSON.stringify(clean)).toContain('12345678-1234-1234-1234-123456789abc')
    expect(JSON.stringify(clean)).not.toContain(TOKEN)
    expect(JSON.stringify(clean)).not.toContain('TokenFromUser')
    expect(JSON.stringify(clean)).not.toContain('evil.test')
  })
  it.each([
    '/app/dist/server/chunks/_.._BXmnJVpK.mjs',
    'file:///app/dist/server/chunks/_.._BXmnJVpK.mjs',
  ])('preserves real Astro dynamic-route stack frames at %s', (filename) => {
    const clean = sanitizeTelemetryProperties({
      $exception_list: [
        { type: 'TypeError', stacktrace: { frames: [{ filename, lineno: 33, colno: 22 }] } },
      ],
    })
    expect(clean?.$exception_list).toEqual([
      {
        type: 'TypeError',
        value: '[redacted]',
        stacktrace: {
          type: 'raw',
          frames: [{ filename, platform: 'node:javascript', lineno: 33, colno: 22 }],
        },
      },
    ])
  })
  it.each([
    'dist/server/chunks/../private.mjs',
    'dist/server/chunks/%2e%2e/private.mjs',
    '/app/dist/server/chunks/../private.mjs',
    'file:///app/dist/server/../../uploads/private.mjs',
    '/app/dist/server/chunks/%2e%2e/private.mjs',
  ])('still strips traversal from stack frames at %s', (filename) => {
    const clean = sanitizeTelemetryProperties({
      $exception_list: [{ type: 'TypeError', stacktrace: { frames: [{ filename, lineno: 1 }] } }],
    })
    expect(clean?.$exception_list).toEqual([{ type: 'TypeError', value: '[redacted]' }])
  })
  it('drops payloads when a getter throws rather than exporting unredacted data', () => {
    expect(
      sanitizeTelemetryProperties({
        get kind() {
          throw new Error('secret')
        },
      })
    ).toBeNull()
  })
  it('does not traverse cyclic unknown context and forces privacy settings', () => {
    const context: Record<string, unknown> = {}
    context.loop = context
    expect(
      sanitizeTelemetryProperties({ context, $geoip_disable: false, $process_person_profile: true })
    ).toEqual({ $geoip_disable: true, $process_person_profile: false })
  })
})

describe('browser capture', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
    vi.doUnmock('posthog-js')
  })
  it('captures once per error with explicit anonymous configuration', async () => {
    vi.stubEnv('PUBLIC_POSTHOG_KEY', 'phc_test')
    const sdk = { init: vi.fn(), register: vi.fn(), captureException: vi.fn() }
    vi.doMock('posthog-js', () => ({ default: sdk }))
    const { captureBrowserException } = await import('@/lib/observability')
    const error = new TypeError('secret')
    await captureBrowserException(error)
    await captureBrowserException(error)
    expect(sdk.captureException).toHaveBeenCalledOnce()
    expect(sdk.init).toHaveBeenCalledWith(
      'phc_test',
      expect.objectContaining({
        api_host: '/ingest',
        persistence: 'memory',
        save_referrer: false,
        save_campaign_params: false,
        person_profiles: 'never',
        capture_exceptions: false,
        disable_session_recording: true,
      })
    )
  })
  it('shares initialization across concurrent early exceptions and retries SDK initialization failures', async () => {
    vi.stubEnv('PUBLIC_POSTHOG_KEY', 'phc_test')
    const sdk = {
      init: vi.fn().mockImplementationOnce(() => {
        throw new Error('temporary')
      }),
      register: vi.fn(),
      captureException: vi.fn(),
    }
    vi.doMock('posthog-js', () => ({ default: sdk }))
    const { captureBrowserException } = await import('@/lib/observability')
    await captureBrowserException(new Error('first'))
    expect(sdk.captureException).not.toHaveBeenCalled()
    await Promise.all([
      captureBrowserException(new Error('second')),
      captureBrowserException(new Error('third')),
    ])
    expect(sdk.init).toHaveBeenCalledTimes(2)
    expect(sdk.captureException).toHaveBeenCalledTimes(2)
    expect(sdk.init.mock.invocationCallOrder[1]).toBeLessThan(
      sdk.captureException.mock.invocationCallOrder[0]
    )
  })
  it('reads flags from the initialized npm singleton without a window global', async () => {
    vi.stubEnv('PUBLIC_POSTHOG_KEY', 'phc_test')
    const sdk = {
      init: vi.fn(),
      register: vi.fn(),
      isFeatureEnabled: vi.fn().mockReturnValue(true),
    }
    vi.doMock('posthog-js', () => ({ default: sdk }))
    const { isFeatureEnabled } = await import('@/lib/feature-flags')
    expect(isFeatureEnabled('saferskills-example-flag')).toBe(false)
    const { initObservability } = await import('@/lib/observability')
    await initObservability()
    expect(isFeatureEnabled('saferskills-example-flag')).toBe(true)
  })
  it('installs global handlers once', async () => {
    const add = vi.spyOn(window, 'addEventListener')
    const { installErrorHandlers } = await import('@/lib/observability')
    installErrorHandlers()
    installErrorHandlers()
    expect(add.mock.calls.filter(([name]) => name === 'error')).toHaveLength(1)
    expect(add.mock.calls.filter(([name]) => name === 'unhandledrejection')).toHaveLength(1)
    add.mockRestore()
  })
  it('does nothing when no project key is configured', async () => {
    vi.stubEnv('PUBLIC_POSTHOG_KEY', '')
    const sdk = { init: vi.fn(), captureException: vi.fn() }
    vi.doMock('posthog-js', () => ({ default: sdk }))
    const { captureBrowserException } = await import('@/lib/observability')
    await captureBrowserException(new Error('local'))
    expect(sdk.init).not.toHaveBeenCalled()
    expect(sdk.captureException).not.toHaveBeenCalled()
  })
})
