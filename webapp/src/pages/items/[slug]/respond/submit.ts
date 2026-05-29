import type { APIRoute } from 'astro'

import { env } from '@/env'
import { jsonResponse, passthrough, VENDOR_SESSION_COOKIE } from '@/lib/vendor-session'

export const prerender = false

/**
 * Submit a vendor response. Reads the HttpOnly `ss_vendor_session` cookie
 * (path-scoped to this endpoint) and forwards the JWT to the backend as a
 * Bearer token — the cookie is never exposed to browser JS. A 401 means the
 * 15-minute session lapsed; the client re-runs the verify flow.
 */
export const POST: APIRoute = async ({ params, request, cookies }) => {
  const { slug } = params
  if (!slug) return jsonResponse({ error: 'bad request' }, 400)

  const sessionToken = cookies.get(VENDOR_SESSION_COOKIE)?.value
  if (!sessionToken) return jsonResponse({ error: 'no vendor session' }, 401)

  let payload: { body_markdown?: string; trigger_rescan?: boolean }
  try {
    payload = await request.json()
  } catch {
    return jsonResponse({ error: 'invalid body' }, 400)
  }

  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/items/${slug}/vendor/responses`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      Authorization: `Bearer ${sessionToken}`,
    },
    body: JSON.stringify({
      body_markdown: payload.body_markdown,
      trigger_rescan: Boolean(payload.trigger_rescan),
    }),
  })

  return passthrough(res)
}
