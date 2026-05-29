import { useEffect } from 'react'
import type { PopularChip } from '@/data/launch-fallbacks'
import type { ScanReportSummary } from '@/lib/api/scans'
import { formatCount, formatSeconds } from '@/lib/format'
import { getHomepageData, type HomepageData } from '@/lib/homepage'

/**
 * Live-refresh island for the prerendered homepage.
 *
 * The static shell is built with the correct build-time values (via
 * `getHomepageData` in `index.astro` frontmatter). This island re-runs the
 * same view-model on the client and patches the existing SSR DOM in place — no
 * structural rewrite, so first paint and the JS-disabled render are untouched
 * and Lighthouse stays ≥90. It renders nothing.
 *
 * Refresh cadence: once on mount, then every 30s, so the page stays fresh
 * between deploys without a reload.
 */

const REFRESH_MS = 30_000

const TIER_TO_SW: Record<string, string> = {
  green: 'green',
  yellow: 'yellow',
  orange: 'orange',
  red: 'orange',
}
const TIER_TO_BAND: Record<string, string> = {
  green: 'Green',
  yellow: 'Yellow',
  orange: 'Orange',
  red: 'Red',
}
const tierIconLetter = (tier: string): string =>
  tier === 'red' || tier === 'orange' ? 'O' : tier === 'yellow' ? 'Y' : 'G'
const tierIconMod = (tier: string): string =>
  tier === 'yellow' ? 'yellow' : tier === 'green' ? '' : 'orange'
const normTier = (tier: string): string => (tier === 'unscoped' ? 'red' : tier)

function patchScalars(data: HomepageData): void {
  const values: Record<string, string> = {
    catalog_total: formatCount(data.catalogTotal),
    median: String(data.medianScore),
    p95: formatSeconds(data.p95LatencyMs),
    avg: formatSeconds(data.avgLatencyMs),
    rule_count: String(data.ruleCount),
    registries: String(data.registriesCount),
    // Note: "stars" is patched by the global NavStars island (Base.astro), which
    // owns the NavBar GhStar count on every page.
  }
  for (const [key, value] of Object.entries(values)) {
    for (const el of document.querySelectorAll<HTMLElement>(`[data-live-stat="${key}"]`)) {
      if (el.textContent !== value) el.textContent = value
    }
  }
}

function patchPopular(chips: PopularChip[]): void {
  const buttons = document.querySelectorAll<HTMLElement>('[data-live-popular] .p1-chip')
  buttons.forEach((btn, i) => {
    const chip = chips[i]
    if (!chip) return
    const nm = btn.querySelector<HTMLElement>('.nm')
    const sc = btn.querySelector<HTMLElement>('.sc')
    if (nm) nm.textContent = chip.name
    if (sc) {
      sc.textContent = String(chip.score)
      sc.className = `sc ${TIER_TO_SW[normTier(chip.tier)] ?? 'green'}`
    }
  })
}

function patchRecentCard(el: HTMLElement, item: ScanReportSummary): void {
  const tier = normTier(item.tier)
  const name = item.title ?? item.slug
  if (el instanceof HTMLAnchorElement) el.href = `/items/${item.slug}`

  const rank = el.querySelector<HTMLElement>('.rank-pill')
  if (rank) rank.textContent = `SCAN · ${item.scanned_at}`

  const nameEl = el.querySelector<HTMLElement>('.name')
  if (nameEl) nameEl.textContent = name

  // Build with DOM nodes + textContent only — author/name flow from
  // anonymous-submitted GitHub URLs, so never interpolate them into innerHTML.
  const meta = el.querySelector<HTMLElement>('.meta')
  if (meta) {
    meta.replaceChildren(document.createTextNode(`${item.author ?? 'unknown'} · skill`))
    const findings = item.findings_count ?? 0
    if (findings > 0) {
      const warn = document.createElement('span')
      warn.className = 'warn'
      warn.textContent = ` · ${findings} finding${findings === 1 ? '' : 's'}`
      meta.appendChild(warn)
    }
  }

  const score = el.querySelector<HTMLElement>('.score-num')
  if (score) {
    const slash = document.createElement('span')
    slash.className = 'slash'
    slash.textContent = '/100'
    score.replaceChildren(document.createTextNode(String(item.aggregate_score)), slash)
  }

  const icon = el.querySelector<HTMLElement>('.icon-mark')
  if (icon) {
    icon.className = `icon-mark ${tierIconMod(tier)}`.trim()
    icon.textContent = tierIconLetter(tier)
  }

  const band = el.querySelector<HTMLElement>('.band')
  if (band) {
    const sw = document.createElement('span')
    sw.className = `sw ${TIER_TO_SW[tier] ?? 'green'}`
    band.replaceChildren(sw, document.createTextNode(TIER_TO_BAND[tier] ?? 'Green'))
  }
}

function patchRecentFeed(recent: ScanReportSummary[]): void {
  recent.forEach((item, i) => {
    const el = document.querySelector<HTMLElement>(`[data-live-card="recent-${i}"]`)
    if (el) patchRecentCard(el, item)
  })
}

function applyAll(data: HomepageData): void {
  patchScalars(data)
  patchPopular(data.popular)
  // Trending stays fallback-only until install counts exist (I-05), so it is
  // intentionally not patched live — only the recently-scanned feed refreshes.
  patchRecentFeed(data.recent)
}

export default function HomepageLive({ initial }: { initial: HomepageData }) {
  useEffect(() => {
    let cancelled = false
    const refresh = async () => {
      const data = await getHomepageData({ ruleCountFallback: initial.ruleCount })
      if (!cancelled) applyAll(data)
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), REFRESH_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [initial.ruleCount])

  return null
}
