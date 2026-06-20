import { describe, expect, it } from 'vitest'

import { datasetJsonLd, serializeJsonLd } from '@/lib/jsonld'
import {
  ANSWER_LEAD,
  answerLead,
  answerLeadWordCount,
  DATASET_META,
  HEADLINE,
  RESEARCH_SLUG,
  RESEARCH_URL,
} from '@/lib/research/state-of'

// The page builds the Dataset url from `Astro.site` (production origin) — mirror
// that here. `RESEARCH_URL` is the production absolute URL, so the descriptor the
// page emits in production is `{ ...DATASET_META, url: RESEARCH_URL }`.
const dataset = { ...DATASET_META, url: RESEARCH_URL }

// SEO-O4 / D-07-06. The `/research/state-of-ai-agent-skill-security` page is a
// hand-authored content page; its copy + headline live in `@/lib/research/state-of`
// so they're testable WITHOUT rendering Astro (the page imports the SAME objects,
// so these pins can never drift from what renders). We assert:
//   - exactly one Dataset JSON-LD carrying the Apache-2.0 license;
//   - the answer-first lead is 40–80 words (the citable-passage budget, V3);
//   - no OpenLatch cross-recommendation anywhere in the copy (brand-independence).
describe('/research state-of report content', () => {
  it('exposes the locked, hand-authored headline (placeholder X% pre-launch)', () => {
    expect(HEADLINE.corpusSize).toBe(500)
    // The audited critical-% ships as the literal placeholder token (outbox/06
    // fills it before launch) — a grep for un-filled placeholders catches it.
    expect(HEADLINE.criticalPct).toBe('__PLACEHOLDER__')
  })

  it('the canonical slug + url are the stable evergreen URL', () => {
    expect(RESEARCH_SLUG).toBe('/research/state-of-ai-agent-skill-security')
    expect(RESEARCH_URL).toBe('https://saferskills.ai/research/state-of-ai-agent-skill-security')
  })

  // V3: the single most durable on-page tactic is a 40–80-word answer-first lead.
  it('the answer-first lead is 40–80 words (the citable-passage budget)', () => {
    const count = answerLeadWordCount()
    expect(count).toBeGreaterThanOrEqual(40)
    expect(count).toBeLessThanOrEqual(80)
  })

  it('resolves the {n}/{pct} tokens against the locked headline', () => {
    const lead = answerLead()
    expect(lead).toContain('500 most-popular')
    expect(lead).toContain('__PLACEHOLDER__%')
    // No un-substituted template token survives into the rendered copy.
    expect(lead).not.toContain('{n}')
    expect(lead).not.toContain('{pct}')
  })

  // BRAND INDEPENDENCE (design-system.md § Anti-recommendation): the page never
  // cross-recommends OpenLatch — footer attribution only. Regression guard over
  // every piece of authored copy on the page.
  it('contains no OpenLatch cross-recommendation (brand independence)', () => {
    const copy = [ANSWER_LEAD, answerLead(), DATASET_META.name, DATASET_META.description]
      .join(' ')
      .toLowerCase()
    expect(copy).not.toContain('openlatch')
  })

  it('emits exactly one Dataset JSON-LD with the Apache-2.0 license', () => {
    const ds = datasetJsonLd(dataset)
    expect(ds['@type']).toBe('Dataset')
    expect(ds.license).toBe('https://www.apache.org/licenses/LICENSE-2.0')
    expect(ds.url).toBe(RESEARCH_URL)
    expect(ds.creator).toMatchObject({ '@type': 'Organization', name: 'SaferSkills' })

    // Serialized as a single Thing (one <script>), never an array → one @graph.
    const parsed = JSON.parse(serializeJsonLd(ds))
    expect(parsed['@context']).toBe('https://schema.org')
    expect(parsed['@type']).toBe('Dataset')
    expect('@graph' in parsed).toBe(false)
  })
})
