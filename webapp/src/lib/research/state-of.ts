/**
 * Hand-authored content for the `/research/state-of-ai-agent-skill-security`
 * State-of report (SEO-O4 / D-07-06).
 *
 * The page is an evergreen, manually-updated content page. The headline **X%**
 * and corpus figures are a *locked, manually-audited* census — NOT a live stat
 * (a drifting number would undermine the defensible HN headline). They ship as
 * placeholders the founder replaces from outbox/06 before launch.
 *
 * This module exists so the page's copy is testable WITHOUT rendering Astro:
 * `state-of-ai-agent-skill-security.astro` imports these constants verbatim, and
 * `research.test.ts` asserts on the same objects (answer-lead word count, the
 * Dataset descriptor, the no-OpenLatch brand-independence guard). Keeping the
 * copy here means the test can never drift from what the page renders.
 *
 * **Brand independence** (`.claude/rules/design-system.md` § Anti-recommendation):
 * none of this copy cross-recommends OpenLatch — footer attribution only. Voice:
 * methodology-over-opinion.
 */

/** Canonical, stable evergreen URL (no trailing slash) — also the sitemap loc. */
export const RESEARCH_SLUG = '/research/state-of-ai-agent-skill-security'
export const RESEARCH_URL = `https://saferskills.ai${RESEARCH_SLUG}`

/**
 * LOCKED, hand-authored numbers — founder fills from outbox/06 before launch.
 * `criticalPct` ships as the literal `__PLACEHOLDER__` token (NOT a number) so a
 * grep for un-filled placeholders catches it pre-launch; `asOf` is the publish
 * date, also placeheld. `corpusSize` (500) is the audited top-N and is final.
 */
export const HEADLINE = {
  /** The audited top-N deep-scanned (final — the "500 most-popular"). */
  corpusSize: 500,
  /** The audited critical-finding rate (outbox/06 fills before launch). */
  criticalPct: '__PLACEHOLDER__',
  /** Publish date (outbox/06 fills before launch). */
  asOf: '2026-__-__',
} as const

/**
 * The answer-first lead (SEO-T7 / V3) — the single citable passage, in visible
 * HTML, carrying the score/finding facts an AI engine quotes with attribution.
 * Hard requirement: 40–80 words (`research.test.ts` pins it). The `{pct}` /
 * `{n}` tokens are substituted at render with `HEADLINE` so the count is stable
 * regardless of the final number (a percentage is one word either way).
 */
export const ANSWER_LEAD =
  'How risky are AI agent skills? SaferSkills independently deep-scanned the ' +
  '{n} most-popular skills and MCP servers across every major registry. ' +
  '{pct}% carried at least one critical security finding. Every result is ' +
  'reproducible from public, Apache-2.0 detection rules, with per-finding ' +
  'evidence and a vendor right-of-reply. The methodology is open and the ' +
  'verdict is appealable. Scan any capability free, in about thirty seconds.'

/** Resolve the answer-lead tokens against the locked headline numbers. */
export function answerLead(headline: typeof HEADLINE = HEADLINE): string {
  return ANSWER_LEAD.replace('{n}', String(headline.corpusSize)).replace(
    '{pct}',
    headline.criticalPct
  )
}

/** Word count of the *resolved* answer-lead (placeholder counts as one word). */
export function answerLeadWordCount(headline: typeof HEADLINE = HEADLINE): number {
  return answerLead(headline).trim().split(/\s+/).length
}

/**
 * The Dataset JSON-LD descriptor — name + description only. The `url` is built
 * in the page from `Astro.site` (so it matches Base's canonical origin and stays
 * env-correct), then passed to `datasetJsonLd`. `RESEARCH_URL` above is the
 * production absolute URL used by the test.
 */
export const DATASET_META = {
  name: 'State of AI Agent Skill Security',
  description:
    'SaferSkills deep-scan of the most-popular AI agent skills and MCP servers — ' +
    'critical-finding rate by category and severity, methodology open (Apache-2.0).',
} as const
