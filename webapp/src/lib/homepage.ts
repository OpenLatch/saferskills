/**
 * Homepage view-model — the one place the live-with-fallback rules run.
 *
 * Fetches every homepage data source in parallel (each error-safe via
 * `fetchOrNull`), runs the fallback pickers, and returns one fully-resolved
 * view-model. The same function runs at build time (in `index.astro`
 * frontmatter → correct static HTML even with an empty catalog and JS disabled)
 * and on the client (in the `HomepageLive` island → fresh between deploys).
 */

import {
  FALLBACK_AVG_LATENCY_MS,
  FALLBACK_CATALOG_TOTAL,
  FALLBACK_GITHUB_STARS,
  FALLBACK_MEDIAN_SCORE,
  FALLBACK_P95_LATENCY_MS,
  FALLBACK_POPULAR,
  FALLBACK_REGISTRIES_COUNT,
  PLACEHOLDER_RECENT,
  PLACEHOLDER_TRENDING,
  type PopularChip,
} from '@/data/launch-fallbacks'
import { listCatalogItems } from '@/lib/api/items'
import {
  listRecentSubmissionScans,
  listTrendingScans,
  type ScanReportSummary,
} from '@/lib/api/scans'
import { fetchPlatformStats, type PlatformStats } from '@/lib/api/stats'
import { fetchOrNull, pickCount, pickList } from '@/lib/fallback'

export interface HomepageData {
  catalogTotal: number
  registriesCount: number
  githubStars: number
  medianScore: number
  p95LatencyMs: number
  avgLatencyMs: number
  ruleCount: number
  agentsCount: number
  recent: ScanReportSummary[]
  trending: ScanReportSummary[]
  popular: PopularChip[]
}

/** Map catalog items (most-installed, scored) to Popular search chips. */
async function fetchPopularChips(): Promise<PopularChip[] | null> {
  const res = await listCatalogItems({ sort: 'most_installed', limit: 6 })
  return res.data
    .filter((i) => typeof i.latest_scan_score === 'number' && i.latest_scan_tier != null)
    .map((i) => ({
      slug: i.slug,
      name: i.display_name,
      score: i.latest_scan_score as number,
      tier: (i.latest_scan_tier ?? 'green') as PopularChip['tier'],
      // Live chips link to the real item page; the fallback constants carry
      // href '/capabilities' (href is resolved on the view-model).
      href: `/items/${i.slug}`,
    }))
}

export interface HomepageFallbackOpts {
  /** Build-time rule count from the generated methodology (the SSOT). */
  ruleCountFallback: number
}

export async function getHomepageData(opts: HomepageFallbackOpts): Promise<HomepageData> {
  const [stats, recentLive, trendingLive, popularLive] = await Promise.all([
    fetchOrNull<PlatformStats>(fetchPlatformStats),
    fetchOrNull(() => listRecentSubmissionScans({ limit: 3 })),
    fetchOrNull(() => listTrendingScans({ limit: 3 })),
    fetchOrNull(fetchPopularChips),
  ])

  return {
    catalogTotal: pickCount(stats?.catalog_total, FALLBACK_CATALOG_TOTAL),
    registriesCount: pickCount(stats?.registries_count, FALLBACK_REGISTRIES_COUNT),
    // Stars are shown honestly: the live repo count whenever GitHub returns a
    // number (even small), falling back to the placeholder ONLY when the proxy
    // is unavailable (null). No ≥10 threshold here — unlike the other scalars,
    // the real star count is never vanity-inflated.
    githubStars: stats?.github_stars ?? FALLBACK_GITHUB_STARS,
    medianScore: pickCount(stats?.median_score, FALLBACK_MEDIAN_SCORE),
    p95LatencyMs: pickCount(stats?.p95_latency_ms, FALLBACK_P95_LATENCY_MS),
    avgLatencyMs: pickCount(stats?.avg_latency_ms, FALLBACK_AVG_LATENCY_MS),
    // rule_count is always meaningful at ≥1; the fallback is the build-time
    // methodology count (same SSOT), so live and fallback never disagree.
    ruleCount: pickCount(stats?.rule_count, opts.ruleCountFallback, 1),
    agentsCount: stats?.agents_count ?? 8,
    recent: pickList(recentLive, PLACEHOLDER_RECENT, 3).slice(0, 3),
    trending: pickList(trendingLive, PLACEHOLDER_TRENDING, 3).slice(0, 3),
    popular: pickList(popularLive, FALLBACK_POPULAR, 3).slice(0, 4),
  }
}
