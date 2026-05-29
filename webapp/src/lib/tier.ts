/**
 * Tier presentation helpers — the single home for score-tier → CSS-class and
 * → hex mappings shared across item components, the badge SVG, and OG cards.
 *
 * The authoritative score→tier ladder lives in the backend
 * (`services/api/app/scan/engine.py`); the frontend only ever consumes the
 * already-projected `tier` string, never re-derives it from a score.
 */

export type ScoredTier = 'green' | 'yellow' | 'orange' | 'red'

/** Tier → the single-letter stripe variant used by `.stripe-l.stripe-<x>`. */
export const TIER_TO_STRIPE: Record<ScoredTier, string> = {
  green: 'g',
  yellow: 'y',
  orange: 'o',
  red: 'r',
}

/**
 * Tier → hex for baked image assets (badge SVG + OG PNG) where CSS variables /
 * design tokens can't resolve. UI components must use tokens, never these.
 */
export const TIER_HEX: Record<string, string> = {
  green: '#10B981',
  yellow: '#F59E0B',
  orange: '#F97316',
  red: '#EF4444',
  unscoped: '#94A3B8',
}

/** Narrow an arbitrary tier string to the 4 scored tiers, or null if unscoped. */
export function scoredTier(tier?: string | null): ScoredTier | null {
  return tier === 'green' || tier === 'yellow' || tier === 'orange' || tier === 'red' ? tier : null
}

/** The full left-stripe class for a tier, or '' when unscored. */
export function stripeClass(tier?: string | null): string {
  const t = scoredTier(tier)
  return t ? `stripe-l stripe-${TIER_TO_STRIPE[t]}` : ''
}
