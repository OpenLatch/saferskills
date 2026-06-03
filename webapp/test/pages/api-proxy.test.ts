import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The proxy reads `process.env.API_ORIGIN` at module-eval, so set it before each
// dynamic import and reset the module registry between cases.
const ORIGIN = 'http://backend.test'

type ProxyContext = Parameters<typeof import('@/pages/api/[...path]').GET>[0]

function ctx(request: Request, path: string, clientAddress = '10.0.0.1'): ProxyContext {
  return { request, params: { path }, clientAddress } as unknown as ProxyContext
}

describe('same-origin /api/* reverse proxy', () => {
  beforeEach(() => {
    process.env.API_ORIGIN = ORIGIN
    // `process.env.X = undefined` coerces to the string "undefined" — delete it.
    delete process.env.SAFERSKILLS_PROXY_SHARED_SECRET
    vi.resetModules()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('forwards path + query to API_ORIGIN and preserves the visitor IP', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response('{"data":[]}', {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
    )
    vi.stubGlobal('fetch', fetchMock)
    const { GET } = await import('@/pages/api/[...path]')

    const request = new Request('http://localhost:5173/api/v1/items?sort=most_installed&limit=6', {
      headers: { accept: 'application/json', 'fly-client-ip': '203.0.113.9' },
    })
    const res = await GET(ctx(request, 'v1/items'))

    expect(res.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledOnce()
    const [target, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(target).toBe(`${ORIGIN}/api/v1/items?sort=most_installed&limit=6`)
    const headers = init.headers as Headers
    expect(headers.get('x-forwarded-for')).toBe('203.0.113.9')
    // Hop-by-hop / host headers are stripped.
    expect(headers.get('host')).toBeNull()
    // No secret configured → no X-Proxy-Secret header.
    expect(headers.get('x-proxy-secret')).toBeNull()
  })

  it('never trusts a client-supplied X-Forwarded-For (uses the TCP peer instead)', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const { GET } = await import('@/pages/api/[...path]')

    // Attacker forges XFF + Fly-Client-IP, with no trusted edge in front.
    const request = new Request('http://localhost:5173/api/v1/scans?limit=1', {
      headers: { 'x-forwarded-for': '1.2.3.4', 'fly-client-ip': '' },
    })
    await GET(ctx(request, 'v1/scans', '198.51.100.20'))

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    // The spoofed value is dropped; the real TCP peer is forwarded instead.
    expect((init.headers as Headers).get('x-forwarded-for')).toBe('198.51.100.20')
  })

  it('sends X-Proxy-Secret when SAFERSKILLS_PROXY_SHARED_SECRET is configured', async () => {
    process.env.SAFERSKILLS_PROXY_SHARED_SECRET = 'top-secret'
    vi.resetModules()
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const { GET } = await import('@/pages/api/[...path]')

    // A browser-supplied X-Proxy-Secret must be overwritten with the real one.
    const request = new Request('http://localhost:5173/api/v1/stats', {
      headers: { 'x-proxy-secret': 'forged-by-client' },
    })
    await GET(ctx(request, 'v1/stats', '203.0.113.4'))

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Headers).get('x-proxy-secret')).toBe('top-secret')
  })

  it('streams a POST body with duplex set', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 202 }))
    vi.stubGlobal('fetch', fetchMock)
    const { POST } = await import('@/pages/api/[...path]')

    const request = new Request('http://localhost:5173/api/v1/scans/upload', {
      method: 'POST',
      body: 'multipart-bytes',
      headers: { 'cf-turnstile-response': 'tok' },
    })
    const res = await POST(ctx(request, 'v1/scans/upload', '198.51.100.7'))

    expect(res.status).toBe(202)
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit & { duplex?: string }]
    expect(init.method).toBe('POST')
    expect(init.duplex).toBe('half')
    // The Turnstile header is passed through to the backend gate.
    expect((init.headers as Headers).get('cf-turnstile-response')).toBe('tok')
  })

  it('strips content-encoding from the response (undici already decoded the body)', async () => {
    // Regression: undici transparently decompresses the upstream body, so the
    // bytes we stream back are plaintext. Re-emitting the upstream
    // `content-encoding: br` made the browser double-decode → the
    // ERR_CONTENT_DECODING_FAILED seen on every /api/* call on staging.
    const fetchMock = vi.fn(
      async () =>
        new Response('{"catalog_total":0}', {
          status: 200,
          headers: { 'content-type': 'application/json', 'content-encoding': 'br' },
        })
    )
    vi.stubGlobal('fetch', fetchMock)
    const { GET } = await import('@/pages/api/[...path]')

    const res = await GET(ctx(new Request('http://localhost:5173/api/v1/stats'), 'v1/stats'))

    expect(res.status).toBe(200)
    // The corrupting header must be gone; content-type stays.
    expect(res.headers.get('content-encoding')).toBeNull()
    expect(res.headers.get('content-type')).toBe('application/json')
    // Body still readable (decoded plaintext, not double-decoded).
    expect(await res.text()).toBe('{"catalog_total":0}')
  })

  it('returns 502 when the backend is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('ECONNREFUSED')
      })
    )
    const { GET } = await import('@/pages/api/[...path]')
    const res = await GET(ctx(new Request('http://localhost:5173/api/v1/stats'), 'v1/stats'))
    expect(res.status).toBe(502)
    expect(await res.json()).toEqual({ error: 'upstream_unreachable' })
  })
})
