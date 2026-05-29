import type { APIRoute } from 'astro'

import { env } from '@/env'
import { jsonResponse, passthrough } from '@/lib/vendor-session'

export const prerender = false

/**
 * Proxy the vendor verify/start to the backend. No cookie involved — the raw
 * token is returned once to the client for the vendor to commit. Same-origin
 * so the React island never makes a cross-origin call.
 */
export const POST: APIRoute = async ({ params }) => {
  const { slug } = params
  if (!slug) return jsonResponse({ error: 'bad request' }, 400)

  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/items/${slug}/vendor/verify/start`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  })
  return passthrough(res)
}
