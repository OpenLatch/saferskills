/**
 * Live-data-with-fallback primitives.
 *
 * The whole "nothing is primarily hardcoded" vision in three functions: every
 * metric originates from a live API call; an impressive launch placeholder
 * survives ONLY as a fallback when the live source is too thin to look good.
 *
 *   - Lists  → live only when it has ≥ `minItems` items (default 3).
 *   - Scalars → live only when it clears the `minCount` floor (default 10).
 *
 * This keeps the page beautiful with an empty catalog (placeholders show) and
 * silently switches to real data as the catalog fills — see
 * `.claude/rules/frontend-patterns.md` § Live data on a prerendered page.
 */

/** List: use the live array only when it has enough items to look good. */
export function pickList<T>(live: T[] | null | undefined, placeholder: T[], minItems = 3): T[] {
  return live != null && live.length >= minItems ? live : placeholder
}

/** Scalar: use the live value only when it clears the floor. */
export function pickCount(
  live: number | null | undefined,
  placeholder: number,
  minCount = 10
): number {
  return typeof live === 'number' && live >= minCount ? live : placeholder
}

/**
 * Error-safe fetch → `null`. Lets the picker decide between live and
 * placeholder instead of scattering `.catch(() => [])` at each call site
 * (which would conflate "fetch failed" with "live but empty").
 */
export async function fetchOrNull<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn()
  } catch {
    return null
  }
}
