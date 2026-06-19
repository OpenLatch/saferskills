import type { APIRoute } from 'astro'

import { env } from '@/env'

/**
 * Apex sitemap — relays the backend-generated `<sitemapindex>`.
 *
 * The backend owns the index + DB shards (tens of thousands of rows enumerated
 * by an indexed SELECT — far cheaper than paging the public API over HTTP). This
 * route runs server-side, so `env.PUBLIC_API_URL` resolves to the runtime
 * `API_ORIGIN` and reaches the backend directly. `robots.txt` advertises this
 * URL (`Sitemap: https://saferskills.ai/sitemap.xml`).
 */
export const prerender = false

export const GET: APIRoute = async () => {
  const upstream = await fetch(`${env.PUBLIC_API_URL}/api/v1/sitemap/index.xml`).catch(() => null)
  if (!upstream || !upstream.ok) {
    return new Response('sitemap upstream unavailable', { status: 502 })
  }
  return new Response(await upstream.text(), {
    status: 200,
    headers: { 'Content-Type': 'application/xml', 'Cache-Control': 'public, max-age=3600' },
  })
}
