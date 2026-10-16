import type { APIRoute } from 'astro'

export const prerender = false
const MAX_BODY_BYTES = 512 * 1024

/** Fixed EU upstreams only. No cookies, authorization, referrers, or visitor IP headers. */
const proxy: APIRoute = async ({ request, params }) => {
  const path = params.path ?? ''
  const asset =
    /^(?:static|array)\/[\w./-]+\.(?:js|json)$/.test(path) ||
    /^array\/phc_[\w]+\/config$/.test(path)
  const endpoint = /^(?:e|batch|decide|flags|i\/v0\/e)\/?$/.test(path)
  if (path.includes('..') || (!asset && !endpoint)) return new Response(null, { status: 404 })
  if (asset && request.method !== 'GET') return new Response(null, { status: 405 })
  if (Number(request.headers.get('content-length')) > MAX_BODY_BYTES)
    return new Response(null, { status: 413 })
  let body: Uint8Array | undefined
  if (request.method === 'POST') {
    const reader = request.body?.getReader()
    const chunks: Uint8Array[] = []
    let size = 0
    while (reader) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > MAX_BODY_BYTES) {
        await reader.cancel()
        return new Response(null, { status: 413 })
      }
      chunks.push(value)
    }
    body = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) {
      body.set(chunk, offset)
      offset += chunk.length
    }
  }
  const target = new URL(
    `/${path}`,
    asset ? 'https://eu-assets.i.posthog.com' : 'https://eu.i.posthog.com'
  )
  target.search = new URL(request.url).search
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers: { 'content-type': request.headers.get('content-type') || 'application/json' },
      body: body as BodyInit | undefined,
      redirect: 'error',
      signal: AbortSignal.timeout(5000),
    })
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'content-type': upstream.headers.get('content-type') || 'application/json',
        'cache-control': asset && upstream.ok ? 'public, max-age=3600' : 'no-store',
      },
    })
  } catch {
    // Do not recursively report a telemetry transport failure through telemetry.
    return new Response(null, { status: 502 })
  }
}
export const GET = proxy
export const POST = proxy
