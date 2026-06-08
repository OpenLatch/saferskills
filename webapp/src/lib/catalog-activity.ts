/**
 * Catalog "Activity" sparkline resolver — the live-with-fallback rule for the
 * per-row install trend (`.claude/rules/frontend-patterns.md` § Live data).
 *
 * Backend returns 13 weekly install counts (oldest→newest). install_events is
 * opt-in CLI telemetry, so early on most rows are all-zero. Rather than render a
 * dead-flat cell, we synthesize a *deterministic* placeholder shape seeded by the
 * item's popularity — stable per row, clearly flagged as a placeholder (the
 * Sparkline's muted/dashed variant), and auto-replaced the moment real installs
 * arrive. No fabricated number is ever shown as if it were real.
 */

export const ACTIVITY_WEEKS = 13

/** Deterministic 0..1 PRNG from an integer seed (mulberry32). */
function seeded(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** FNV-1a string hash → 32-bit int, so the placeholder shape is unique per row. */
function hashKey(key: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

export interface ActivitySeries {
  values: number[]
  /** true → render the muted/dashed placeholder (no real install signal). */
  placeholder: boolean
}

/**
 * Resolve the activity series for a row. Real data (any non-zero week) wins;
 * otherwise a deterministic placeholder is returned — its SHAPE seeded by
 * `seedKey` (the slug, so every row looks distinct) and its AMPLITUDE scaled by
 * popularity (a more-popular row reads as a touch livelier). Purely decorative.
 */
export function resolveActivity(
  real: number[] | null | undefined,
  popularityScore: number,
  seedKey = ''
): ActivitySeries {
  const series = real ?? []
  if (series.some((v) => v > 0)) return { values: series, placeholder: false }

  const rand = seeded(hashKey(seedKey) ^ (Math.round(popularityScore) * 2654435761 + 1))
  const amp = Math.max(2, Math.min(10, Math.round(popularityScore / 12) + 2))
  const values = Array.from({ length: ACTIVITY_WEEKS }, (_, i) => {
    const trend = (i / (ACTIVITY_WEEKS - 1)) * amp * 0.45
    return Math.round(trend + rand() * amp * 0.7)
  })
  return { values, placeholder: true }
}
