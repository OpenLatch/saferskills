/**
 * Per-page OG-image URL derivation (SEO-T5). Pure helpers so the page templates
 * stay thin and the "only a finished, scored run gets a dynamic card; otherwise
 * fall back to the static branded card" rule is unit-testable (mirrors
 * `isIndexableScan` driving the noindex prop).
 *
 * Returns `undefined` when the page should fall back to the static `/og-image.png`
 * (`Base.astro` substitutes the default for an undefined `ogImage`):
 *   - a scan that is not `completed` (pending / running / failed) has no real
 *     score to card — must match the scan-OG endpoint's `status !== 'completed'`
 *     404 guard so the advertised URL never 404s;
 *   - an ungraded agent run (`score == null`) has no number to card.
 *
 * `site` is `Astro.site` (the configured origin). Callers pass `.href` of the
 * returned `URL` into `<Base ogImage={...}>`.
 */

/** `/og/scan/<id>.png` only for a COMPLETED run; `undefined` otherwise (pending /
 * running / failed). Mirrors the endpoint's completed-only 404 guard. */
export function scanOgImage(id: string, status: string, site: URL | undefined): string | undefined {
  if (status !== 'completed') return undefined
  return new URL(`/og/scan/${id}.png`, site).href
}

/** `/og/agent/<id>.png` for a graded run; `undefined` when ungraded (score null). */
export function agentOgImage(
  id: string,
  score: number | null,
  site: URL | undefined
): string | undefined {
  if (score == null) return undefined
  return new URL(`/og/agent/${id}.png`, site).href
}
