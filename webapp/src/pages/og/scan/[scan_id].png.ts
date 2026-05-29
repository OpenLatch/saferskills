import type { APIRoute } from 'astro'

import { fetchScanById } from '@/lib/api/scans'
import { OG_HEADERS, renderOgCard } from '@/lib/og'

export const prerender = false

/** Per-scan 1200×630 social-share card. */
export const GET: APIRoute = async ({ params }) => {
  const { scan_id } = params
  if (!scan_id) return new Response('Bad request', { status: 400 })

  const scan = await fetchScanById(scan_id).catch(() => null)
  if (!scan) return new Response('Scan not found', { status: 404 })

  const png = await renderOgCard({
    displayName: scan.display_name || scan.slug,
    score: scan.aggregate_score,
    tier: scan.tier,
    footer: `saferskills.ai/scans/${scan.id.slice(0, 12)}`,
  })

  return new Response(new Uint8Array(png), { status: 200, headers: OG_HEADERS })
}
