// @vitest-environment node
import { gunzipSync } from 'node:zlib'
import { PostHog } from 'posthog-node'
import { afterEach, expect, it, vi } from 'vitest'
import { sanitizeTelemetryProperties } from '@/lib/telemetry-privacy'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('keeps the Node SDK relative bundle frame and chunk ID through exception capture', async () => {
  vi.spyOn(process, 'cwd').mockReturnValue('/app')
  const error = new TypeError('private submitted input')
  error.stack =
    'TypeError: private submitted input\n    at proxy (file:///app/dist/server/chunks/_.._probe.mjs:33:22)'
  const chunkId = '01234567-89ab-cdef-0123-456789abcdef'
  vi.stubGlobal('_posthogChunkIds', { [error.stack]: chunkId })
  const beforeSend = vi.fn(sanitizeTelemetryProperties)
  const delivered: unknown[] = []
  const client = new PostHog('phc_test', {
    fetchRetryCount: 0,
    before_send: (event) => {
      const properties = beforeSend(event.properties)
      return properties ? { ...event, properties } : null
    },
    fetch: async (_url, options) => {
      const body = options.body
      if (!body) throw new Error('Expected event payload')
      const bytes =
        typeof body === 'string'
          ? Buffer.from(body)
          : Buffer.from(body instanceof Blob ? await body.arrayBuffer() : body)
      delivered.push(JSON.parse((bytes[0] === 31 ? gunzipSync(bytes) : bytes).toString('utf8')))
      return { status: 200, text: async () => 'OK', json: async () => ({ status: 1 }) }
    },
  })
  try {
    await client.captureExceptionImmediate(error, 'anonymous-server', { service: 'webapp-server' })
    const frame = {
      filename: 'dist/server/chunks/_.._probe.mjs',
      platform: 'node:javascript',
      chunk_id: chunkId,
      lineno: 33,
      colno: 22,
      function: 'proxy',
    }
    expect(beforeSend).toHaveBeenCalledWith(
      expect.objectContaining({
        $exception_list: [
          expect.objectContaining({
            stacktrace: expect.objectContaining({ frames: [expect.objectContaining(frame)] }),
          }),
        ],
      })
    )
    expect(delivered).toEqual([
      expect.objectContaining({
        batch: [
          expect.objectContaining({
            event: '$exception',
            properties: expect.objectContaining({
              $exception_list: [
                {
                  type: 'TypeError',
                  value: '[redacted]',
                  stacktrace: { type: 'raw', frames: [frame] },
                },
              ],
            }),
          }),
        ],
      }),
    ])
    expect(JSON.stringify(delivered)).not.toContain('private submitted input')
  } finally {
    await client.shutdown()
  }
})
