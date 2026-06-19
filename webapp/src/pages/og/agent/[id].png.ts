import type { APIRoute } from 'astro'

import { fetchAgentScanRunById } from '@/lib/api/agent-scans'
import { OG_HEADERS, renderOgCard } from '@/lib/og'

export const prerender = false

/**
 * Per-agent-scan 1200×630 social-share card for a public, graded Agent Report.
 * Mirrors `og/scan/[scan_id].png.ts`. `id` is an agent-run id (the `/agents/<id>`
 * report id). An unlisted run is NEVER card-able (anti-leakage — we must not mint
 * a public image for a token-only run), and an ungraded run (`score == null`) has
 * no number to render → both 404.
 */
export const GET: APIRoute = async ({ params }) => {
  const { id } = params
  if (!id) return new Response('Bad request', { status: 400 })

  const run = await fetchAgentScanRunById(id).catch(() => null)
  if (!run || run.visibility === 'unlisted' || run.score == null) {
    return new Response('Agent scan not found', { status: 404 })
  }

  const png = await renderOgCard({
    displayName: run.agent_name ?? 'agent scan',
    score: run.score,
    tier: run.band,
    footer: `saferskills.ai/agents/${run.id.slice(0, 12)}`,
  })

  return new Response(new Uint8Array(png), { status: 200, headers: OG_HEADERS })
}
