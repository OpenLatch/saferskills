import type { APIRoute } from 'astro'

import { fetchAgentScanRunById } from '@/lib/api/agent-scans'
import { escapeHtml } from '@/lib/rule-prose'
import { TIER_HEX } from '@/lib/tier'

export const prerender = false

/**
 * Behavioral Agent Scan badge (~300×60 SVG) for a public agent RUN — the `id`
 * segment is an `agent_runs` id (the same id the `/agents/<id>` report + the
 * directory expose). The badge re-renders from the LIVE report: it validates the
 * `score` URL segment against the run's current behavioral score and, on a
 * mismatch (a tampered `/99.svg`), 302-redirects to the correct `…/{liveScore}.svg`
 * rather than render the forged value (anti-forgery). Unlisted /
 * ungraded runs are never badgeable (404). Adds a behavioral band label + a
 * trust-tier glyph over the scan badge. Edge-cached 1h.
 */
export const GET: APIRoute = async ({ params, redirect }) => {
  const { id, score } = params
  if (!id || !score) return new Response('Bad request', { status: 400 })

  const expectedScore = Number.parseInt(score, 10)
  if (Number.isNaN(expectedScore)) return new Response('Invalid score', { status: 400 })

  const run = await fetchAgentScanRunById(id).catch(() => null)
  if (!run || run.score === null || run.band === 'unscoped') {
    return new Response('Agent scan not found', { status: 404 })
  }
  // Anti-forgery: a tampered score never renders — redirect to the live value.
  if (run.score !== expectedScore) {
    return redirect(`/badge/agent/${encodeURIComponent(id)}/${run.score}.svg`, 302)
  }

  const bandColor = TIER_HEX[run.band] ?? TIER_HEX.unscoped
  const bandLabel = escapeHtml(run.band.toUpperCase())
  const liveScore = run.score

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="60" viewBox="0 0 300 60" role="img" aria-label="SaferSkills Agent behavioral score ${liveScore} of 100, ${bandLabel} band">
  <title>SaferSkills Agent · ${liveScore} / 100 · ${bandLabel}</title>
  <rect x="0.5" y="0.5" width="299" height="59" fill="#FFFFFF" stroke="#0F172A" stroke-width="1"/>
  <g transform="translate(16, 18)">
    <rect width="24" height="24" fill="#0D9488"/>
    <path d="M5 6 H19 L15 10 H5 Z M5 14 H19 L15 18 H5 Z" fill="#FFFFFF"/>
  </g>
  <text x="50" y="26" font-family="'DM Sans', system-ui, sans-serif" font-weight="600" font-size="14" fill="#0F172A">SaferSkills</text>
  <text x="50" y="42" font-family="'Space Mono', ui-monospace, monospace" font-weight="400" font-size="9" fill="#64748B" letter-spacing="0.08em">AGENT SCAN</text>
  <line x1="146" y1="14" x2="146" y2="46" stroke="#CBD5E1" stroke-width="1"/>
  <text x="162" y="38" font-family="'DM Sans', system-ui, sans-serif" font-weight="800" font-size="24" fill="#0F172A" letter-spacing="-0.04em">${liveScore}</text>
  <text x="${liveScore >= 100 ? 210 : 192}" y="38" font-family="'Space Mono', ui-monospace, monospace" font-weight="400" font-size="11" fill="#94A3B8">/100</text>
  <rect x="226" y="25" width="10" height="10" fill="${bandColor}"/>
  <text x="240" y="34" font-family="'Space Mono', ui-monospace, monospace" font-weight="700" font-size="9" fill="#0F172A" letter-spacing="0.1em">${bandLabel}</text>
  <g transform="translate(276, 22)" aria-hidden="true">
    <path d="M8 0 L15 3 V8 C15 12 12 15 8 16 C4 15 1 12 1 8 V3 Z" fill="none" stroke="${bandColor}" stroke-width="1.4"/>
    <path d="M5 8 L7.2 10.2 L11 5.6" fill="none" stroke="${bandColor}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
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
