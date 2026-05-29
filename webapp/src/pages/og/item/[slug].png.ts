import type { APIRoute } from 'astro'

import { fetchItemBySlug } from '@/lib/api/items'
import { OG_HEADERS, renderOgCard } from '@/lib/og'

export const prerender = false

/** Per-item 1200×630 social-share card (uses the item's latest scan). */
export const GET: APIRoute = async ({ params }) => {
  const { slug } = params
  if (!slug) return new Response('Bad request', { status: 400 })

  const detail = await fetchItemBySlug(slug).catch(() => null)
  if (!detail) return new Response('Item not found', { status: 404 })

  const png = await renderOgCard({
    displayName: detail.item.display_name,
    score: detail.latest_scan?.aggregate_score ?? null,
    tier: detail.latest_scan?.tier ?? 'unscoped',
    footer: `saferskills.ai/items/${slug}`,
  })

  return new Response(new Uint8Array(png), { status: 200, headers: OG_HEADERS })
}
