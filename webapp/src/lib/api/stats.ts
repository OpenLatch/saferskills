import { env } from '@/env'

/**
 * Homepage platform metrics. Hand-written to match the existing `lib/api/*.ts`
 * convention; the wire shape is the backend `PlatformStats` (snake_case keys).
 * Every scalar is nullable so the fallback pickers can decide live-vs-placeholder.
 */
export interface PlatformStats {
  catalog_total: number
  registries_count: number
  tier_distribution: Record<string, number>
  median_score: number | null
  p95_latency_ms: number | null
  avg_latency_ms: number | null
  rule_count: number
  agents_count: number
  github_stars: number | null
}

export async function fetchPlatformStats(): Promise<PlatformStats> {
  const res = await fetch(`${env.PUBLIC_API_URL}/api/v1/stats`, {
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return (await res.json()) as PlatformStats
}
