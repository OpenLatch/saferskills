import type { APIRoute } from 'astro'

import { fetchScanRunById } from '@/lib/api/scans'
import { TIER_HEX } from '@/lib/tier'

export const prerender = false

function esc(value: string): string {
  return value.replace(/[<>&"]/g, (c) =>
    c === '<' ? '&lt;' : c === '>' ? '&gt;' : c === '&' ? '&amp;' : '&quot;'
  )
}

/**
 * Permalink-style scan badge (~280×60 SVG) for a public scan RUN — the `scan_id`
 * segment is a run id (the same id the `/scans/<id>` report, the public feed, and
 * the embed-badge box expose; the public `/scans` list returns run ids, not
 * per-capability scan ids). Validates the `score` URL segment against the run's
 * repo aggregate score (or one of its capabilities' scores — the per-file upload
 * badge embeds a capability score) so a tampered URL (`/99.svg`) can't inflate a
 * badge — a mismatch is a 400. Unlisted runs are never badgeable (404).
 * Edge-cached 1h.
 */
export const GET: APIRoute = async ({ params }) => {
  const { scan_id, score } = params
  if (!scan_id || !score) return new Response('Bad request', { status: 400 })

  const expectedScore = Number.parseInt(score, 10)
  if (Number.isNaN(expectedScore)) return new Response('Invalid score', { status: 400 })

  const run = await fetchScanRunById(scan_id).catch(() => null)
  if (!run || run.visibility === 'unlisted') {
    return new Response('Scan not found', { status: 404 })
  }
  const matchedTier =
    run.repo_aggregate_score === expectedScore
      ? run.repo_tier
      : run.capabilities.find((c) => c.aggregate_score === expectedScore)?.tier
  if (!matchedTier) return new Response('Score mismatch', { status: 400 })

  const tierColor = TIER_HEX[matchedTier] ?? TIER_HEX.unscoped
  const tierLabel = esc(matchedTier.toUpperCase())

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="280" height="60" viewBox="0 0 280 60" role="img" aria-label="SaferSkills score ${expectedScore} of 100, ${tierLabel} tier">
  <title>SaferSkills score ${expectedScore} / 100 — ${tierLabel}</title>
  <rect x="0.5" y="0.5" width="279" height="59" fill="#FFFFFF" stroke="#0F172A" stroke-width="1"/>
  <g transform="translate(16, 18)">
    <rect width="24" height="24" fill="#0D9488"/>
    <path d="M5 6 H19 L15 10 H5 Z M5 14 H19 L15 18 H5 Z" fill="#FFFFFF"/>
  </g>
  <text x="50" y="35" font-family="'DM Sans', system-ui, sans-serif" font-weight="600" font-size="16" fill="#0F172A">SaferSkills</text>
  <line x1="158" y1="14" x2="158" y2="46" stroke="#CBD5E1" stroke-width="1"/>
  <text x="176" y="38" font-family="'DM Sans', system-ui, sans-serif" font-weight="800" font-size="24" fill="#0F172A" letter-spacing="-0.04em">${expectedScore}</text>
  <text x="${expectedScore >= 100 ? 224 : 206}" y="38" font-family="'Space Mono', ui-monospace, monospace" font-weight="400" font-size="11" fill="#94A3B8">/100</text>
  <rect x="234" y="25" width="10" height="10" fill="${tierColor}"/>
  <text x="248" y="34" font-family="'Space Mono', ui-monospace, monospace" font-weight="700" font-size="9" fill="#0F172A" letter-spacing="0.12em">${tierLabel}</text>
</svg>`

  return new Response(svg, {
    status: 200,
    headers: {
      'Content-Type': 'image/svg+xml; charset=utf-8',
      'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400',
      'X-Robots-Tag': 'noindex',
    },
  })
}
