import type { APIRoute } from 'astro'

import { fetchScanRunById } from '@/lib/api/scans'
import { OG_HEADERS, renderOgCard } from '@/lib/og'
import { reportIdentity } from '@/lib/report-identity'

export const prerender = false

/**
 * Per-scan 1200×630 social-share card for a public scan RUN. `scan_id` is a run id
 * (the `/scans/<id>` report id the public feed + share surfaces expose), so it is
 * resolved via `fetchScanRunById`, never the per-capability `/scans/<id>` endpoint.
 * Only a COMPLETED public run is card-able — an unlisted run (anti-leakage) or a
 * pending/running/failed run (no real score to render) is never carded (404).
 */
export const GET: APIRoute = async ({ params }) => {
  const { scan_id } = params
  if (!scan_id) return new Response('Bad request', { status: 400 })

  const run = await fetchScanRunById(scan_id).catch(() => null)
  if (!run || run.visibility === 'unlisted' || run.status !== 'completed') {
    return new Response('Scan not found', { status: 404 })
  }

  const { isUpload, uploadName, repoName } = reportIdentity(run)
  const png = await renderOgCard({
    displayName: (isUpload ? uploadName : repoName) || 'scan',
    score: run.repo_aggregate_score,
    tier: run.repo_tier,
    footer: `saferskills.ai/scans/${run.id.slice(0, 12)}`,
  })

  return new Response(new Uint8Array(png), { status: 200, headers: OG_HEADERS })
}
