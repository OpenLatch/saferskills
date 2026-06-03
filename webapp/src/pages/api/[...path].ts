import type { APIRoute } from 'astro'

/**
 * Same-origin API reverse proxy.
 *
 * The browser calls `/api/*` on the webapp's own origin; this route forwards
 * each request to the backend API. That keeps the client URL same-origin (no
 * CORS, no per-environment URL baked into the bundle) and lives entirely in the
 * app — no edge/CDN rule required, so the deployment stays portable across hosts.
 *
 * The target is `API_ORIGIN`: a runtime, server-only var (NOT `PUBLIC_*`, never
 * shipped to the client) set per environment (`webapp/fly.*.toml`, compose).
 * Falls back to localhost for local `pnpm dev`.
 *
 * Streaming (not buffering) the request + response bodies is required so this
 * transparently carries JSON, `.zip` downloads, `text/event-stream` SSE
 * (scan progress), and multipart uploads.
 *
 * See `.claude/rules/frontend-patterns.md` § Same-origin API proxy and
 * `.claude/rules/security.md` § Public-input handling.
 */
export const prerender = false

const API_ORIGIN = (
  (typeof process !== 'undefined' && process.env.API_ORIGIN) ||
  'http://localhost:8000'
).replace(/\/+$/, '')

// Shared secret proving to the backend that this request really came from the
// proxy (server-only runtime var, never shipped to the client). The API trusts
// the forwarded visitor IP only when `X-Proxy-Secret` matches, so a direct
// caller to the public API cannot spoof `X-Forwarded-For`. Unset → no header
// (dev/test); the API then keys rate limits on the raw peer.
const SAFERSKILLS_PROXY_SHARED_SECRET =
  (typeof process !== 'undefined' && process.env.SAFERSKILLS_PROXY_SHARED_SECRET) || ''

// RFC 7230 hop-by-hop headers — never forwarded across a proxy boundary.
// `content-length` is dropped too: bodies are streamed (chunked), so a stale
// length would corrupt the framing. `host` must reflect the upstream, not us.
const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'host',
  'content-length',
])

function forwardableHeaders(source: Headers): Headers {
  const out = new Headers()
  for (const [key, value] of source) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) out.set(key, value)
  }
  return out
}

const proxy: APIRoute = async ({ request, params, clientAddress }) => {
  const path = params.path ?? ''
  const search = new URL(request.url).search
  const target = `${API_ORIGIN}/api/${path}${search}`

  const headers = forwardableHeaders(request.headers)

  // Set the real visitor IP for the backend per-IP rate limiter from a TRUSTED
  // source only. On Fly the edge OVERWRITES `Fly-Client-IP` with the actual
  // client, so it is authoritative; off Fly (local/dev) the TCP peer is. We do
  // NOT fall back to the client's `X-Forwarded-For` — that header is attacker-
  // controlled, and because the proxy also presents the shared secret the API
  // would otherwise trust a spoofed value as the rate-limit key. Strip BOTH
  // inbound forwarding headers first so a client value can never reach the
  // backend even partially, then set ours. (A different edge/CDN would mean
  // trusting a different documented header here.)
  headers.delete('x-forwarded-for')
  headers.delete('fly-client-ip')
  // `||` (not `??`) so an empty/whitespace edge header also falls back to the peer.
  const visitor = request.headers.get('fly-client-ip')?.trim() || clientAddress
  if (visitor) headers.set('x-forwarded-for', visitor)
  // `set` (not append) means a browser can neither inject a fake secret nor read
  // the real one; the API trusts the forwarded IP only on a secret match.
  if (SAFERSKILLS_PROXY_SHARED_SECRET)
    headers.set('x-proxy-secret', SAFERSKILLS_PROXY_SHARED_SECRET)

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: 'manual',
  }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = request.body
    // Node's fetch requires `duplex: 'half'` to send a streaming request body.
    ;(init as RequestInit & { duplex: 'half' }).duplex = 'half'
  }

  let upstream: Response
  try {
    upstream = await fetch(target, init)
  } catch {
    return new Response(JSON.stringify({ error: 'upstream_unreachable' }), {
      status: 502,
      headers: { 'content-type': 'application/json' },
    })
  }

  // Pipe the upstream body straight back — never `.text()`/`.json()` it, or SSE
  // and large downloads would buffer in memory and stall.
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: forwardableHeaders(upstream.headers),
  })
}

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
export const HEAD = proxy
export const OPTIONS = proxy
