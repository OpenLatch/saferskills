import { afterEach, describe, expect, it, vi } from 'vitest'
import { GET, POST } from '@/pages/ingest/[...path]'

type Context = Parameters<typeof GET>[0]
const ctx = (path: string, request: Request) =>
  ({ params: { path }, request }) as unknown as Context

afterEach(() => vi.unstubAllGlobals())
describe('fixed EU telemetry proxy', () => {
  it('forwards events without cookies, credentials, or visitor IP', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response('{}', { headers: { 'set-cookie': 'bad=1' } }))
    vi.stubGlobal('fetch', fetch)
    const response = await POST(
      ctx(
        'i/v0/e/',
        new Request('http://localhost/ingest/i/v0/e/', {
          method: 'POST',
          body: '{}',
          headers: { cookie: 'private=1', authorization: 'secret', 'x-forwarded-for': '1.2.3.4' },
        })
      )
    )
    expect(fetch.mock.calls[0][0].origin).toBe('https://eu.i.posthog.com')
    expect(fetch.mock.calls[0][1].headers).toEqual({ 'content-type': 'text/plain;charset=UTF-8' })
    expect(response.headers.has('set-cookie')).toBe(false)
  })
  it('serves the SDK extensionless project configuration from the fixed EU asset host', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await GET(
      ctx('array/phc_test/config', new Request('http://localhost/ingest/array/phc_test/config'))
    )
    expect(fetch.mock.calls[0][0].href).toBe(
      'https://eu-assets.i.posthog.com/array/phc_test/config'
    )
  })
  it.each([
    'https://evil.test',
    '../batch',
    'static/../secret.js',
    'api/projects/272364',
  ])('rejects non-ingestion path %s', async (path) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect((await GET(ctx(path, new Request('http://localhost/ingest/test')))).status).toBe(404)
    expect(fetch).not.toHaveBeenCalled()
  })
  it('rejects excessive bodies before contacting the upstream', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect(
      (
        await POST(
          ctx(
            'e/',
            new Request('http://localhost/ingest/e/', {
              method: 'POST',
              body: 'x'.repeat(512 * 1024 + 1),
            })
          )
        )
      ).status
    ).toBe(413)
    expect(fetch).not.toHaveBeenCalled()
  })
  it('turns transport failures into a bounded 502 without recursive reporting', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    expect((await GET(ctx('flags/', new Request('http://localhost/ingest/flags/')))).status).toBe(
      502
    )
  })
})
