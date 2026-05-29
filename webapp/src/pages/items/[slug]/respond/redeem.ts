import type { APIRoute } from 'astro'

import { env } from '@/env'
import {
  jsonResponse,
  VENDOR_SESSION_COOKIE,
  vendorSessionCookieOptions,
} from '@/lib/vendor-session'

export const prerender = false

/**
 * Redeem a verification token. Proxies to the backend, which validates the
 * `.saferskills/verify.txt` file and mints the session JWT. On success this
 * endpoint sets the HttpOnly `ss_vendor_session` cookie **on the webapp origin**
 * (so the SSR respond page can read it) and returns `{ ok: true }`. The client
 * then reloads into the verified branch.
 */
export const POST: APIRoute = async ({ params, request, cookies }) => {
  const { slug } = params
  if (!slug) return jsonResponse({ error: 'bad request' }, 400)

  let payload: { token?: string; github_user?: string }
  try {
    payload = await request.json()
  } catch {
    return jsonResponse({ error: 'invalid body' }, 400)
  }

  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/items/${slug}/vendor/verify/redeem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ token: payload.token, github_user: payload.github_user }),
  })

  if (!res.ok) {
    const detail = await safeDetail(res)
    return jsonResponse({ error: detail }, res.status)
  }

  const data = (await res.json()) as { session_jwt: string }
  cookies.set(VENDOR_SESSION_COOKIE, data.session_jwt, vendorSessionCookieOptions(slug))
  return jsonResponse({ ok: true })
}

async function safeDetail(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string }
    return data.detail ?? `verification failed (${res.status})`
  } catch {
    return `verification failed (${res.status})`
  }
}
