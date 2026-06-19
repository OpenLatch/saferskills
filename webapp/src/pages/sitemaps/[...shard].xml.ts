import type { APIRoute } from 'astro'

import { env } from '@/env'
import { renderStaticShard } from '@/lib/seo/static-sitemap'

/**
 * Sitemap shard relay.
 *
 * `static`  → the webapp-owned shard (prerendered marketing + docs URLs the
 *             backend can't enumerate).
 * otherwise → relayed from the backend DB shard
 *             (`/api/v1/sitemap/shard/<shard>.xml`).
 *
 * Serves at `/sitemaps/<shard>.xml` (Astro strips the `.ts`); a sitemap URL has
 * no trailing slash, so the file-extension endpoint resolves cleanly.
 */
export const prerender = false

const XML_HEADERS = { 'Content-Type': 'application/xml', 'Cache-Control': 'public, max-age=3600' }

export const GET: APIRoute = async ({ params }) => {
  const shard = params.shard
  if (!shard) return new Response('bad request', { status: 400 })

  if (shard === 'static') {
    return new Response(await renderStaticShard(), { status: 200, headers: XML_HEADERS })
  }

  const upstream = await fetch(`${env.PUBLIC_API_URL}/api/v1/sitemap/shard/${shard}.xml`).catch(
    () => null
  )
  if (!upstream || !upstream.ok) {
    return new Response('sitemap shard unavailable', {
      status: upstream?.status === 404 ? 404 : 502,
    })
  }
  return new Response(await upstream.text(), { status: 200, headers: XML_HEADERS })
}
