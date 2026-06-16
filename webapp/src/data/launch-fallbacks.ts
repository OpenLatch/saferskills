/**
 * Launch-day fallback values.
 *
 * Used ONLY as a fallback when the live API is below threshold — never a
 * primary source. Every value here is an impressive placeholder that keeps the
 * homepage beautiful while the catalog is still small; the moment real data
 * crosses the threshold (`pickCount` ≥ 10, `pickList` ≥ 3) the true value
 * replaces it. See `.claude/rules/frontend-patterns.md` and the founder-approved
 * "cliff" consequence (honesty over vanity once real data exists).
 *
 * Genuine config (SUPPORTED_AGENTS, DETECTION_TILES, ATTACK_GRID, rotating
 * nouns) stays in `homepage-constants.ts`.
 */

import type { ScanReportSummary, ScanTier } from '@/lib/api/scans'

// ── Scalars ────────────────────────────────────────────────────────────────
export const FALLBACK_CATALOG_TOTAL = 12_847
export const FALLBACK_REGISTRIES_COUNT = 12
export const FALLBACK_GITHUB_STARS = 26_908
export const FALLBACK_MEDIAN_SCORE = 76
export const FALLBACK_P95_LATENCY_MS = 30_000 // "30s p95"
export const FALLBACK_AVG_LATENCY_MS = 28_000 // "avg 28s"

// ── "Popular" search chips ───────────────────────────────────────────────────
export type PopularChip = {
  slug: string
  name: string
  score: number
  tier: ScanTier
  /**
   * Chip destination, resolved at view-model construction (D-5.7-13):
   * live chips link to the real `/items/<slug>` page; fallback chips link to
   * `/capabilities` (their slugs are placeholders — a 404 would betray the
   * fallback). `pickList` erases live-vs-fallback provenance, so the href
   * MUST ride on the chip itself.
   */
  href: string
}

export const FALLBACK_POPULAR: PopularChip[] = [
  {
    slug: 'anthropic--claude-pdf',
    name: 'claude-pdf',
    score: 95,
    tier: 'green',
    href: '/capabilities',
  },
  {
    slug: 'github--github-mcp',
    name: 'github-mcp',
    score: 87,
    tier: 'green',
    href: '/capabilities',
  },
  { slug: 'alice--slack-bot', name: 'slack-bot', score: 71, tier: 'yellow', href: '/capabilities' },
  {
    slug: 'linear--linear-mcp',
    name: 'linear-mcp',
    score: 92,
    tier: 'green',
    href: '/capabilities',
  },
]

// ── Feeds mosaic (recently-scanned + trending) ───────────────────────────────
export const PLACEHOLDER_RECENT: ScanReportSummary[] = [
  {
    id: 'ph-r1',
    github_url: '',
    slug: 'acme--github-mcp',
    title: 'github-mcp',
    author: 'acme',
    aggregate_score: 87,
    tier: 'green',
    scanned_at: '2m ago',
    findings_count: 0,
  },
  {
    id: 'ph-r2',
    github_url: '',
    slug: 'alice--slack-bot',
    title: 'slack-bot',
    author: 'alice',
    aggregate_score: 42,
    tier: 'orange',
    scanned_at: '5m ago',
    findings_count: 2,
  },
  {
    id: 'ph-r3',
    github_url: '',
    slug: 'tana--obsidian-mcp',
    title: 'obsidian-mcp',
    author: 'tana',
    aggregate_score: 71,
    tier: 'yellow',
    scanned_at: '8m ago',
    findings_count: 1,
  },
]

export const PLACEHOLDER_TRENDING: ScanReportSummary[] = [
  {
    id: 'ph-t1',
    github_url: '',
    slug: 'linear--mcp',
    title: 'linear-mcp',
    author: 'linear',
    aggregate_score: 96,
    tier: 'green',
    scanned_at: '7d',
    findings_count: 0,
  },
  {
    id: 'ph-t2',
    github_url: '',
    slug: 'notion--mcp',
    title: 'notion-mcp',
    author: 'notion',
    aggregate_score: 88,
    tier: 'green',
    scanned_at: '7d',
    findings_count: 0,
  },
  {
    id: 'ph-t3',
    github_url: '',
    slug: 'neon--mcp',
    title: 'neon-mcp',
    author: 'neon',
    aggregate_score: 84,
    tier: 'green',
    scanned_at: '7d',
    findings_count: 0,
  },
]

/** Per-rank trending stats — installs are not yet tracked (I-05), so these
 * back the trending cards until real install counts exist. */
export const TREND_STATS = [
  { installs: 1247, delta: 312, spark: '▁▂▂▃▅▇█' },
  { installs: 873, delta: 94, spark: '▁▂▃▃▄▆▇' },
  { installs: 612, delta: 58, spark: '▁▁▂▃▄▅▆' },
]
