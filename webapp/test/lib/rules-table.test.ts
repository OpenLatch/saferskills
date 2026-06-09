import { describe, expect, it } from 'vitest'
import { ruleRows } from '@/generated/methodology/rules-table'

/**
 * Locks the framework-badge coverage of the generated rule table so a new rule
 * cannot silently ship unmapped. The authoritative split is enforced first by the
 * generator (scripts/generate-methodology.cjs EXPECTED_BADGED / EXPECTED_UNBADGED);
 * this mirrors it on the generated output the webapp actually ships.
 */
const EXPECTED_BADGED = 39
const EXPECTED_UNBADGED = 16

describe('methodology rule table', () => {
  it('matches the expected badged / unbadged split', () => {
    const badged = ruleRows.filter((r) => r.frameworks.length > 0).length
    const unbadged = ruleRows.length - badged
    expect(badged).toBe(EXPECTED_BADGED)
    expect(unbadged).toBe(EXPECTED_UNBADGED)
    expect(ruleRows.length).toBe(EXPECTED_BADGED + EXPECTED_UNBADGED)
  })

  it('every badged ref carries a resolvable family + url', () => {
    for (const row of ruleRows) {
      for (const f of row.frameworks) {
        expect(['owasp-llm', 'mitre-atlas', 'cwe']).toContain(f.family)
        expect(f.url).toMatch(/^https:\/\//)
        expect(f.id.length).toBeGreaterThan(0)
      }
    }
  })

  it('exposes the plain-English name as a non-empty first-column value', () => {
    for (const row of ruleRows) {
      expect(row.name.length).toBeGreaterThan(0)
      expect(row.name).not.toMatch(/^SS-/)
    }
  })
})
