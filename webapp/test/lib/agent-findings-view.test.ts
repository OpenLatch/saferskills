import { describe, expect, it } from 'vitest'
import {
  findingRefChips,
  groupFindingsByFamily,
  MITRE_ATLAS_URL,
  owaspIndex,
  refToChip,
  scoreMathFor,
} from '@/lib/agent/findings-view'
import type { AgentFindingRow, AgentScoreBreakdown } from '@/lib/api/agent-scan-types'

function f(over: Partial<AgentFindingRow>): AgentFindingRow {
  return {
    id: 'x',
    test_id: 'AS-06',
    severity: 'critical',
    verdict: 'vulnerable',
    family: 'Tool-description poisoning',
    owasp_refs: ['ASI04:2026'],
    atlas_refs: ['AML.T0053'],
    nist_refs: ['NIST AI 600-1'],
    score_delta: -40,
    detection_rule: 'tool_arg',
    leaked_canary_slot: 'AS-06',
    title: 't',
    explanation: 'e',
    severity_rationale: null,
    category_label: null,
    remediation: { action: 'a', steps: null, safer_pattern: null },
    evidence_excerpt: null,
    ...over,
  } as AgentFindingRow
}

describe('refToChip', () => {
  it('maps OWASP / MITRE / NIST refs to deep-links and drops unknowns', () => {
    expect(refToChip('ASI04:2026')?.kind).toBe('owasp')
    expect(refToChip('LLM01:2025')?.kind).toBe('owasp')
    const mitre = refToChip('AML.T0053')
    expect(mitre?.kind).toBe('mitre')
    expect(mitre?.href).toBe(`${MITRE_ATLAS_URL}/techniques/AML.T0053`)
    expect(refToChip('NIST AI 600-1')?.kind).toBe('nist')
    expect(refToChip('weird-ref')).toBeNull()
  })
})

describe('findingRefChips + owaspIndex', () => {
  it('collects owasp+atlas+nist chips and derives the family index', () => {
    expect(findingRefChips(f({}))).toHaveLength(3)
    expect(owaspIndex(['ASI04:2026'])).toBe('ASI04')
    expect(owaspIndex([])).toBe('')
  })
})

describe('groupFindingsByFamily', () => {
  it('groups by family in first-seen order with a deduped chip row', () => {
    const groups = groupFindingsByFamily([
      f({ id: '1', test_id: 'AS-06', family: 'Tool-description poisoning' }),
      f({
        id: '2',
        test_id: 'AS-09',
        family: 'Unsafe code execution',
        owasp_refs: ['ASI05:2026'],
        atlas_refs: [],
      }),
      f({ id: '3', test_id: 'AS-06b', family: 'Tool-description poisoning' }),
    ])
    expect(groups.map((g) => g.family)).toEqual([
      'Tool-description poisoning',
      'Unsafe code execution',
    ])
    expect(groups[0].index).toBe('ASI04')
    expect(groups[0].findings).toHaveLength(2)
    // duplicate ASI04 refs collapse to one chip (owasp ASI04 + atlas AML.T0053)
    expect(groups[0].refs.filter((r) => r.label === 'ASI04:2026')).toHaveLength(1)
  })
})

describe('scoreMathFor', () => {
  const bd: AgentScoreBreakdown = {
    findings: [
      { test_id: 'AS-06', severity: 'critical', score_delta: -40 },
      { test_id: 'AS-09', severity: 'high', score_delta: -25 },
    ],
    raw_score: 35,
    ceiling: 15,
    ceiling_applied: true,
    final_score: 15,
    band_mapping: 'score 15 -> band red',
  }

  it('derives base = raw − Σdelta and emphasizes the matching row', () => {
    const m = scoreMathFor(bd, 'AS-06')
    expect(m?.base).toBe(100) // 35 − (−65)
    expect(m?.modifiers.find((x) => x.testId === 'AS-06')?.emphasized).toBe(true)
    expect(m?.cap).toEqual({ label: 'Worst-finding cap', value: 15 })
    expect(m?.finalScore).toBe(15)
  })

  it('omits the cap when the ceiling was not applied, and null when no breakdown', () => {
    const m = scoreMathFor({ ...bd, ceiling_applied: false, final_score: 35 }, 'AS-06')
    expect(m?.cap).toBeNull()
    expect(scoreMathFor(null, 'AS-06')).toBeNull()
  })
})
