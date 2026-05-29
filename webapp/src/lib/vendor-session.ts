import type { AstroCookieSetOptions } from 'astro'

/**
 * Cookie contract for the vendor right-of-reply session.
 *
 * The webapp owns this HttpOnly cookie (set on redeem, read on submit + on the
 * respond SSR page). It stores the opaque HS256 JWT the API minted; the API is
 * the sole verifier. `Path` is scoped to the slug's respond surface so the
 * cookie is sent only to `/items/<slug>/respond/*` and never leaks to other
 * requests. 15-minute lifetime matches the JWT `exp`.
 */
export const VENDOR_SESSION_COOKIE = 'ss_vendor_session'

export const VENDOR_SESSION_MAX_AGE = 900 // 15 minutes, matches the JWT exp

export function vendorSessionCookieOptions(slug: string): AstroCookieSetOptions {
  return {
    httpOnly: true,
    // `secure` breaks on http://localhost dev; enable only in prod builds.
    secure: import.meta.env.PROD,
    sameSite: 'strict',
    path: `/items/${slug}/respond`,
    maxAge: VENDOR_SESSION_MAX_AGE,
  }
}

/** JSON Response shorthand for the vendor respond endpoints. */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Relay an upstream backend Response verbatim (status + JSON body). */
export async function passthrough(res: Response): Promise<Response> {
  return new Response(await res.text(), {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
